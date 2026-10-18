"""Roles and Company permission for Accounts SaaS tenant users.

The Tenant User Assignment (platform doctype) is the source of truth: its
``role_profile`` decides the Frappe roles, its ``company`` the one Company the
user may work in. Sync runs on assignment save and on migrate, never per request.
"""

from __future__ import annotations

import frappe
from frappe import _

from reckon_accounts_saas.constants import MANAGED_ROLES, MODULE_KEY, PROFILE_ROLES


def company_uses_accounts(company: str | None) -> bool:
    if not company:
        return False
    from reckon_saas_platform.saas import get_company_module_keys

    return MODULE_KEY in get_company_module_keys(company)


def sync_tenant_user_access(doc, method=None) -> None:
    """Tenant User Assignment ``on_update``."""
    if not company_uses_accounts(doc.get("company")):
        return
    sync_user(doc.get("user"))


def sync_user(user: str | None) -> None:
    """Make the user's roles and Company permission match their assignments."""
    if not user or user in {"Guest", "Administrator"} or not frappe.db.exists("User", user):
        return
    assignments = frappe.get_all(
        "Tenant User Assignment",
        filters={"user": user, "active": 1},
        fields=["company", "role_profile"],
    )
    accounts_rows = [row for row in assignments if company_uses_accounts(row.company)]
    wanted = {
        role
        for row in accounts_rows
        for role in PROFILE_ROLES.get(row.role_profile or "", ())
        if frappe.db.exists("Role", role)
    }
    current = set(frappe.get_roles(user))
    user_doc = frappe.get_doc("User", user)
    stale = (current & MANAGED_ROLES) - wanted - _roles_kept_by_other_modules(user, assignments)
    if stale:
        user_doc.remove_roles(*sorted(stale))
    missing = wanted - current
    if missing:
        user_doc.add_roles(*sorted(missing))
    companies = {row.company for row in assignments if row.company}
    if len(companies) == 1:
        sync_company_permission(user, next(iter(companies)))
    elif not companies:
        sync_company_permission(user, None)


def _roles_kept_by_other_modules(user: str, assignments) -> set[str]:
    """ERPNext roles another module may also grant; only remove our own ones then."""
    if all(company_uses_accounts(row.company) for row in assignments):
        return set()
    return {role for role in MANAGED_ROLES if not role.startswith("Reckon Accounts SaaS")}


def sync_company_permission(user: str, company: str | None) -> None:
    """One default Company User Permission applying to all doctypes (idempotent).

    Reckon Distribution keeps the same permission; both apps converge on it.
    """
    existing = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        fields=["name", "for_value", "apply_to_all_doctypes", "is_default"],
    )
    keep = next((row for row in existing if company and row.for_value == company), None)
    for row in existing:
        if not keep or row.name != keep.name:
            frappe.delete_doc("User Permission", row.name, ignore_permissions=True, force=True)
    if keep and not (keep.apply_to_all_doctypes and keep.is_default):
        frappe.db.set_value(
            "User Permission", keep.name, {"apply_to_all_doctypes": 1, "is_default": 1}
        )
    if company and not keep:
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": "Company",
                "for_value": company,
                "apply_to_all_doctypes": 1,
                "is_default": 1,
            }
        ).insert(ignore_permissions=True)
    frappe.clear_cache(user=user)


def backfill_accounts_users() -> None:
    """``after_migrate``: repair every Accounts tenant user once."""
    if not frappe.db.exists("DocType", "Tenant User Assignment"):
        return
    users = set(frappe.get_all("Tenant User Assignment", filters={"active": 1}, pluck="user"))
    for user in sorted(users):
        try:
            sync_user(user)
        except Exception:
            frappe.log_error(title=_("Accounts SaaS user sync failed"), message=frappe.get_traceback())
