"""Tenant isolation for ERPNext sales, purchase, stock and accounting records.

Every hook here answers one question for a tenant user: does this record belong
to the user's single tenant Company? Vendor administrators (and Administrator)
bypass through ``reckon_saas_platform.tenant_security.user_can_bypass_tenant``,
which already refuses bypass to anyone holding a tenant assignment.

Three kinds of record:
- documents with a native ``company`` field (invoices, ledgers, warehouses...)
- owned masters (Customer, Supplier, Item...) carrying ``rd_company``
- shared-or-owned taxonomies (Item Group, Brand...): unowned rows are shared
"""

from __future__ import annotations

import frappe
from frappe import _
from reckon_saas_platform.tenant_security import (
    TenantResolutionError,
    require_tenant,
    user_can_bypass_tenant,
)

from reckon_accounts_saas.constants import (
    COMPANY_DOCTYPES,
    MASTER_COMPANY_FIELD,
    OWNED_MASTERS,
    SHARED_OR_OWNED_MASTERS,
)

WRITE_PERMISSIONS = frozenset({"create", "write", "delete", "submit", "cancel", "amend"})
PARTY_DOCTYPES = frozenset({"Customer", "Supplier"})


def tenant_company(user: str | None = None) -> str | None:
    """The tenant Company of ``user``; ``None`` for vendor administrators."""
    user = user or frappe.session.user
    if user_can_bypass_tenant(user):
        return None
    return require_tenant(user=user).company


# ---------------------------------------------------------------------------
# List and link-search conditions (permission_query_conditions)


def get_company_document_query(user: str | None = None, doctype: str | None = None) -> str:
    company = tenant_company(user)
    if company is None or doctype not in COMPANY_DOCTYPES:
        return ""
    return f"`tab{doctype}`.`company` = {frappe.db.escape(company)}"


def get_company_query(user: str | None = None, doctype: str | None = None) -> str:
    company = tenant_company(user)
    if company is None:
        return ""
    return f"`tabCompany`.`name` = {frappe.db.escape(company)}"


def get_owned_master_query(user: str | None = None, doctype: str | None = None) -> str:
    company = tenant_company(user)
    if company is None:
        return ""
    if not doctype or not frappe.db.has_column(doctype, MASTER_COMPANY_FIELD):
        return "1=0"
    column = f"`tab{doctype}`.`{MASTER_COMPANY_FIELD}`"
    if doctype in SHARED_OR_OWNED_MASTERS:
        return f"({column} is null or {column} = '' or {column} = {frappe.db.escape(company)})"
    return f"{column} = {frappe.db.escape(company)}"


def get_bin_query(user: str | None = None, doctype: str | None = None) -> str:
    """Bin has no company; scope it through its Warehouse."""
    company = tenant_company(user)
    if company is None:
        return ""
    return (
        "`tabBin`.`warehouse` in (select name from `tabWarehouse` "
        f"where company = {frappe.db.escape(company)})"
    )


def get_user_query(user: str | None = None, doctype: str | None = None) -> str:
    """Tenant users see their own login and their colleagues, not other tenants."""
    user = user or frappe.session.user
    company = tenant_company(user)
    if company is None:
        return ""
    return (
        f"(`tabUser`.`name` = {frappe.db.escape(user)} or `tabUser`.`name` in ("
        "select `user` from `tabTenant User Assignment` "
        f"where company = {frappe.db.escape(company)}))"
    )


# ---------------------------------------------------------------------------
# Document checks (has_permission)


def has_company_document_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    company = _company_or_none(user)
    if company is None:
        return True
    permission_type = ptype or permission_type
    value = doc.get("company")
    if doc.is_new() and permission_type in {"create", "write"}:
        return value in (None, "", company)
    stored = frappe.db.get_value(doc.doctype, doc.name, "company") if not doc.is_new() else value
    return stored == company and value in (None, "", company)


def has_company_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    company = _company_or_none(user)
    if company is None:
        return True
    permission_type = ptype or permission_type
    if permission_type in {"create", "delete"}:
        return False
    return doc.name == company


def has_owned_master_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    company = _company_or_none(user)
    if company is None:
        return True
    permission_type = ptype or permission_type
    value = doc.get(MASTER_COMPANY_FIELD)
    if doc.is_new():
        return value in (None, "", company)
    stored = frappe.db.get_value(doc.doctype, doc.name, MASTER_COMPANY_FIELD)
    if doc.doctype in SHARED_OR_OWNED_MASTERS and not stored:
        # Shared taxonomy rows are readable by everyone and changeable by no tenant.
        return permission_type not in WRITE_PERMISSIONS
    return stored == company and value in (None, "", company)


def has_bin_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    company = _company_or_none(user)
    if company is None:
        return True
    return frappe.db.get_value("Warehouse", doc.get("warehouse"), "company") == company


def has_user_permission(doc, user=None, ptype=None, permission_type=None, debug=False) -> bool:
    user = user or frappe.session.user
    company = _company_or_none(user)
    if company is None or doc.name == user:
        return True
    permission_type = ptype or permission_type
    if permission_type in WRITE_PERMISSIONS:
        return False
    return bool(frappe.db.exists("Tenant User Assignment", {"user": doc.name, "company": company}))


def _company_or_none(user: str | None) -> str | None:
    try:
        return tenant_company(user)
    except TenantResolutionError:
        # A logged-in user without a tenant and without bypass sees nothing.
        return "\0no-tenant"


# ---------------------------------------------------------------------------
# Save-time binding and cross-tenant reference checks (doc_events)


def bind_company_document(doc, method=None) -> None:
    """``before_validate``: stamp the tenant Company and keep it immutable."""
    company = tenant_company()
    if company is None or not doc.meta.has_field("company"):
        return
    if doc.get("company") and doc.get("company") != company:
        frappe.throw(_("This document belongs to another company."), frappe.PermissionError)
    if not doc.is_new() and frappe.db.get_value(doc.doctype, doc.name, "company") != company:
        frappe.throw(_("This document belongs to another company."), frappe.PermissionError)
    doc.company = company


def validate_company_document(doc, method=None) -> None:
    """``validate``: every party, item, warehouse and account must be the tenant's."""
    company = tenant_company()
    if company is None:
        return
    for party_field, party_type_field, fixed_type in (
        ("customer", None, "Customer"),
        ("supplier", None, "Supplier"),
        ("party", "party_type", None),
        ("party_name", "quotation_to", None),
    ):
        if not doc.meta.has_field(party_field) or not doc.get(party_field):
            continue
        party_type = fixed_type or doc.get(party_type_field)
        if party_type in PARTY_DOCTYPES:
            assert_owned_master(party_type, doc.get(party_field), company)
    for field in ("set_warehouse", "set_target_warehouse", "from_warehouse", "to_warehouse"):
        if doc.meta.has_field(field) and doc.get(field):
            assert_company_record("Warehouse", doc.get(field), company)
    for field in ("selling_price_list", "buying_price_list"):
        if doc.meta.has_field(field) and doc.get(field):
            assert_owned_master("Price List", doc.get(field), company, allow_shared=True)
    for row in _child_rows(doc):
        if row.get("item_code"):
            assert_owned_master("Item", row.get("item_code"), company)
        for field in ("warehouse", "s_warehouse", "t_warehouse", "target_warehouse", "from_warehouse"):
            if row.get(field):
                assert_company_record("Warehouse", row.get(field), company)
        if row.get("account"):
            assert_company_record("Account", row.get("account"), company)
        if row.get("party") and row.get("party_type") in PARTY_DOCTYPES:
            assert_owned_master(row.get("party_type"), row.get("party"), company)


def bind_owned_master(doc, method=None) -> None:
    """``before_validate`` on owned masters: stamp and protect the owner."""
    company = tenant_company()
    if company is None or not doc.meta.has_field(MASTER_COMPANY_FIELD):
        return
    value = doc.get(MASTER_COMPANY_FIELD)
    if doc.is_new():
        if value and value != company:
            frappe.throw(_("This record belongs to another company."), frappe.PermissionError)
        doc.set(MASTER_COMPANY_FIELD, company)
        return
    stored = frappe.db.get_value(doc.doctype, doc.name, MASTER_COMPANY_FIELD)
    if stored != company or (value and value != company):
        frappe.throw(_("This record belongs to another company."), frappe.PermissionError)
    doc.set(MASTER_COMPANY_FIELD, company)


def assert_owned_master(doctype: str, name: str, company: str, allow_shared: bool = False) -> None:
    owner = frappe.db.get_value(doctype, name, MASTER_COMPANY_FIELD)
    if owner == company or (allow_shared and not owner and frappe.db.exists(doctype, name)):
        return
    frappe.throw(_("{0} {1} is not available in your company.").format(_(doctype), name), frappe.PermissionError)


def assert_company_record(doctype: str, name: str, company: str) -> None:
    if frappe.db.get_value(doctype, name, "company") != company:
        frappe.throw(_("{0} {1} is not available in your company.").format(_(doctype), name), frappe.PermissionError)


def _child_rows(doc):
    for df in doc.meta.get_table_fields():
        yield from doc.get(df.fieldname) or []


def owned_master_doctypes() -> tuple[str, ...]:
    return OWNED_MASTERS + SHARED_OR_OWNED_MASTERS
