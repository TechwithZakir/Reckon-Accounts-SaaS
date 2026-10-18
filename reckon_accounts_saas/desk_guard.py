"""Read-only Desk and API boundary for Accounts SaaS tenant users.

Runs as ``before_request`` after the platform subscription gate. It never writes
or clears caches. For tenants that subscribe to several modules it allows the
union of every subscribed module's pages, doctypes and reports (each module
publishes them in its ``reckon_saas_modules`` definition).

API calls are also checked for parameters that name another tenant's record,
and query-report filters are pinned to the tenant Company.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

import frappe
from frappe import _
from reckon_saas_platform.tenant_security import user_can_bypass_tenant

from reckon_accounts_saas.constants import (
    ALLOWED_DOCTYPES,
    ALLOWED_PAGES,
    ALLOWED_REPORTS,
    HOME_ROUTE,
    LOOKUP_ONLY_DOCTYPES,
    MASTER_COMPANY_FIELD,
    MODULE_KEY,
    SCOPED_PARAMETERS,
)

GENERIC_DESK_API_PREFIXES = (
    "frappe.client.",
    "frappe.desk.reportview.",
    "frappe.desk.form.",
    "frappe.desk.search.",
)
REPORT_METHOD_PREFIX = "frappe.desk.query_report."
API_METHOD_PREFIXES = ("/api/method/", "/api/v1/method/", "/api/v2/method/")
API_RESOURCE_PREFIXES = ("/api/resource/", "/api/v1/resource/", "/api/v2/document/")
DESK_PREFIXES = ("/app", "/desk")


class TenantScope:
    """What one tenant user may reach."""

    def __init__(self, company: str, modules: list[str]):
        self.company = company
        self.modules = modules
        self.pages, self.doctypes, self.reports = _allowed_for(modules)
        self.routes = self.pages | {
            frappe.scrub(dt).replace("_", "-") for dt in self.doctypes - LOOKUP_ONLY_DOCTYPES
        }


def get_accounts_scope(user: str | None = None) -> TenantScope | None:
    """The scope when ``user`` is an Accounts tenant; ``None`` otherwise."""
    user = user or frappe.session.user
    if not user or user in {"Guest", "Administrator"} or user_can_bypass_tenant(user):
        return None
    from reckon_saas_platform.saas import get_company_module_keys
    from reckon_saas_platform.tenant_security import get_user_companies

    companies = get_user_companies(user)
    if len(companies) != 1:
        return None
    modules = get_company_module_keys(companies[0])
    if MODULE_KEY not in modules:
        return None
    return TenantScope(companies[0], modules)


def restrict_accounts_desk_request() -> None:
    """``before_request`` hook."""
    frappe.flags.accounts_saas_redirect = None
    if getattr(frappe.flags, "saas_gate_blocked", False):
        return
    scope = get_accounts_scope()
    if scope is None:
        return

    path = _request_path()
    method = _requested_method(path)
    if method is not None:
        _guard_method(method, scope)
        return
    if path.startswith(API_RESOURCE_PREFIXES):
        prefix = next(p for p in API_RESOURCE_PREFIXES if path.startswith(p))
        doctype = unquote(path.removeprefix(prefix).split("/", 1)[0])
        _assert_doctype(doctype, scope)
        return
    if not path.startswith(DESK_PREFIXES):
        return
    route = path.split("/", 3)[2] if path.count("/") >= 2 else ""
    if path.rstrip("/") in DESK_PREFIXES or not route:
        _redirect(HOME_ROUTE)
        return
    route = unquote(route)
    if route not in scope.routes:
        _redirect(HOME_ROUTE)
        return
    if route == "query-report":
        report = unquote(path.split("/query-report/", 1)[-1]).strip("/") if "/query-report/" in path else ""
        if report and report not in scope.reports:
            _redirect(HOME_ROUTE)


def redirect_accounts_desk_response(response, request) -> None:
    """``after_request`` hook: the subscription gate's redirect always wins."""
    location = getattr(frappe.flags, "accounts_saas_redirect", None)
    if not location or response is None or getattr(frappe.flags, "saas_gate_redirect", None):
        return
    response.status_code = 302
    response.headers["Location"] = location
    response.set_data(b"")


def get_user_home_page(user: str):
    """``get_website_user_home_page`` hook, chained with other modules' hooks."""
    scope = get_accounts_scope(user)
    if scope is not None:
        from reckon_saas_platform.saas_gate import is_user_gated

        return "reckonerp-subscription" if is_user_gated(user) else HOME_ROUTE.lstrip("/")
    own = "reckon_accounts_saas.desk_guard.get_user_home_page"
    for hook in frappe.get_hooks("get_website_user_home_page") or []:
        if hook != own:
            result = frappe.get_attr(hook)(user)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------


def _guard_method(method: str, scope: TenantScope) -> None:
    form = frappe.local.form_dict
    _assert_scoped_parameters(form, scope)
    args = _json_dict(form.get("args"))
    if args:
        _assert_scoped_parameters(args, scope)

    if method == "frappe.desk.desk_page.getpage":
        page = form.get("page") or form.get("name")
        if page not in scope.pages:
            frappe.throw(_("Page {0} is not available.").format(page), frappe.PermissionError)
        return
    if method.startswith(REPORT_METHOD_PREFIX):
        report = form.get("report_name") or form.get("report") or (args or {}).get("report_name")
        if report and report not in scope.reports:
            frappe.throw(_("Report {0} is not available.").format(report), frappe.PermissionError)
        _pin_report_company(form, scope.company)
        return
    if method.startswith(GENERIC_DESK_API_PREFIXES):
        doctype = form.get("doctype") or (args or {}).get("doctype")
        if doctype:
            _assert_doctype(doctype, scope)


def _pin_report_company(form, company: str) -> None:
    """Reports run raw SQL; force their company filter to the tenant's."""
    raw = form.get("filters")
    filters = _json_dict(raw) if isinstance(raw, str) else raw
    if filters is None and raw not in (None, ""):
        frappe.throw(_("Report filters are not valid."), frappe.ValidationError)
    filters = dict(filters or {})
    filters["company"] = company
    form["filters"] = json.dumps(filters) if isinstance(raw, str) or raw is None else filters


def _assert_scoped_parameters(values, scope: TenantScope) -> None:
    for parameter, doctype in SCOPED_PARAMETERS.items():
        value = values.get(parameter)
        if not value or not isinstance(value, str):
            continue
        if not _belongs_to_tenant(doctype, value, scope.company):
            frappe.throw(_("{0} {1} is not available in your company.").format(_(doctype), value), frappe.PermissionError)
    party, party_type = values.get("party"), values.get("party_type")
    if isinstance(party, str) and party and party_type in {"Customer", "Supplier"}:
        if not _belongs_to_tenant(party_type, party, scope.company):
            frappe.throw(_("{0} {1} is not available in your company.").format(_(party_type), party), frappe.PermissionError)


def _belongs_to_tenant(doctype: str, name: str, company: str) -> bool:
    if doctype == "Company":
        return name == company
    if doctype in {"Warehouse", "Account", "Cost Center"}:
        stored = frappe.db.get_value(doctype, name, "company")
        return stored is None or stored == company  # unknown names fail later, not here
    if not frappe.db.has_column(doctype, MASTER_COMPANY_FIELD):
        return True
    row = frappe.db.get_value(doctype, name, MASTER_COMPANY_FIELD, as_dict=True)
    if row is None:
        return True
    owner = row.get(MASTER_COMPANY_FIELD)
    return owner == company or (doctype == "Price List" and not owner)


def _assert_doctype(doctype: str, scope: TenantScope) -> None:
    if doctype not in scope.doctypes:
        frappe.throw(_("{0} is not available in your workspace.").format(_(doctype)), frappe.PermissionError)


def _allowed_for(modules: list[str]) -> tuple[set[str], set[str], set[str]]:
    pages, doctypes, reports = set(ALLOWED_PAGES), set(ALLOWED_DOCTYPES), set(ALLOWED_REPORTS)
    from reckon_saas_platform.module_registry import get_saas_modules

    for module in get_saas_modules():
        if module.get("key") in modules and module.get("key") != MODULE_KEY:
            pages.update(module.get("desk_pages") or [])
            doctypes.update(module.get("desk_doctypes") or [])
            reports.update(module.get("desk_reports") or [])
    return pages, doctypes, reports


def _json_dict(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip().startswith("{"):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _requested_method(path: str) -> str | None:
    for prefix in API_METHOD_PREFIXES:
        if path.startswith(prefix):
            return unquote(path.removeprefix(prefix).split("/", 1)[0])
    cmd = (getattr(frappe.local, "form_dict", None) or {}).get("cmd")
    return cmd if isinstance(cmd, str) and cmd else None


def _redirect(location: str) -> None:
    # Raising a redirect in before_request renders a 500; after_request swaps it.
    frappe.flags.accounts_saas_redirect = location


def _request_path() -> str:
    request = getattr(frappe.local, "request", None)
    return (request.path or "") if request else ""
