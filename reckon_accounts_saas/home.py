"""Data for the Accounts SaaS home page: today's numbers and what to do next."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, nowdate

from reckon_accounts_saas.constants import MASTER_COMPANY_FIELD, TEAM_MANAGER_ROLES
from reckon_accounts_saas.tenant import tenant_company


@frappe.whitelist()
def get_home_data(company: str | None = None) -> dict:
    company = _resolve_company(company)
    today = getdate(nowdate())
    month_start = get_first_day(today)
    currency = frappe.db.get_value("Company", company, "default_currency") or "BDT"
    return {
        "company": company,
        "currency": currency,
        "can_manage_team": bool(TEAM_MANAGER_ROLES.intersection(frappe.get_roles())),
        "kpis": {
            "sales_today": _sum("Sales Invoice", "base_grand_total", company, posting_date=today),
            "sales_month": _sum("Sales Invoice", "base_grand_total", company, posting_date=[">=", month_start]),
            "purchase_month": _sum("Purchase Invoice", "base_grand_total", company, posting_date=[">=", month_start]),
            "receivable": _sum("Sales Invoice", "outstanding_amount", company, outstanding_amount=[">", 0]),
            "payable": _sum("Purchase Invoice", "outstanding_amount", company, outstanding_amount=[">", 0]),
            "cash_bank": _cash_bank_balance(company),
            "stock_value": _stock_value(company),
        },
        "recent_sales": _recent("Sales Invoice", "customer_name", company),
        "recent_purchases": _recent("Purchase Invoice", "supplier_name", company),
        "low_stock": _low_stock(company),
        "checklist": _checklist(company),
    }


def _resolve_company(company: str | None) -> str:
    tenant = tenant_company()
    if tenant is not None:
        return tenant  # a tenant never chooses another company
    company = company or frappe.defaults.get_user_default("Company")
    if not company or not frappe.has_permission("Company", "read", company):
        frappe.throw(_("Choose a company."), frappe.PermissionError)
    return company


def _sum(doctype: str, field: str, company: str, **filters) -> float:
    rows = frappe.get_all(
        doctype,
        filters={"company": company, "docstatus": 1, **filters},
        fields=[field],
        limit_page_length=0,
    )
    return flt(sum(flt(row.get(field)) for row in rows), 2)


def _cash_bank_balance(company: str) -> float:
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0},
        pluck="name",
    )
    if not accounts:
        return 0.0
    rows = frappe.get_all(
        "GL Entry",
        filters={"company": company, "account": ["in", accounts], "is_cancelled": 0},
        fields=["debit", "credit"],
        limit_page_length=0,
    )
    return flt(sum(flt(r.debit) - flt(r.credit) for r in rows), 2)


def _stock_value(company: str) -> float:
    warehouses = frappe.get_all("Warehouse", filters={"company": company}, pluck="name")
    if not warehouses:
        return 0.0
    rows = frappe.get_all(
        "Bin", filters={"warehouse": ["in", warehouses]}, fields=["stock_value"], limit_page_length=0
    )
    return flt(sum(flt(r.stock_value) for r in rows), 2)


def _low_stock(company: str, limit: int = 6) -> list[dict]:
    warehouses = frappe.get_all("Warehouse", filters={"company": company}, pluck="name")
    if not warehouses:
        return []
    return frappe.get_all(
        "Bin",
        filters={"warehouse": ["in", warehouses], "actual_qty": ["<=", 0], "projected_qty": ["<", 0]},
        fields=["item_code", "warehouse", "actual_qty", "projected_qty"],
        order_by="projected_qty asc",
        limit_page_length=limit,
    )


def _recent(doctype: str, party_field: str, company: str, limit: int = 5) -> list[dict]:
    # Plain field names only: Frappe v16 rejects SQL expressions in ``fields``.
    rows = frappe.get_all(
        doctype,
        filters={"company": company, "docstatus": ["<", 2]},
        fields=["name", party_field, "posting_date", "grand_total", "outstanding_amount", "status"],
        order_by="creation desc",
        limit_page_length=limit,
    )
    for row in rows:
        row["party"] = row.pop(party_field, None)
    return rows


def _checklist(company: str) -> list[dict]:
    def count(doctype, filters):
        return frappe.db.count(doctype, filters)

    steps = [
        ("items", _("Add your products or services"), "Item", count("Item", {MASTER_COMPANY_FIELD: company})),
        ("customers", _("Add your customers"), "Customer", count("Customer", {MASTER_COMPANY_FIELD: company}) - 1),
        ("suppliers", _("Add your suppliers"), "Supplier", count("Supplier", {MASTER_COMPANY_FIELD: company}) - 1),
        (
            "opening_stock",
            _("Enter opening stock"),
            "Stock Reconciliation",
            count("Stock Reconciliation", {"company": company, "docstatus": 1}),
        ),
        (
            "first_sale",
            _("Create your first sales invoice"),
            "Sales Invoice",
            count("Sales Invoice", {"company": company, "docstatus": 1}),
        ),
        (
            "team",
            _("Invite your team"),
            "accounts-team",
            count("Tenant User Assignment", {"company": company, "active": 1}) - 1,
        ),
    ]
    return [{"key": key, "label": label, "target": target, "done": total > 0} for key, label, target, total in steps]
