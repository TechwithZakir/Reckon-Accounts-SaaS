"""Day-one setup for a new Accounts SaaS company.

Called by the platform's tenant seed job as ``run_accounts_seed(company, seed_version)``
inside a savepoint. Every step is get-or-create, so a retry after a failure is safe.
Only generic placeholders are created: no customers' data, prices or balances.
Office Expense Settings (categories, cash payment method, cost center) come from
Reckon Accounts so the Office Expense form works on day one.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate, nowdate
from reckon_accounts.office_expense_setup import ensure_office_expense_defaults

from reckon_accounts_saas.constants import MASTER_COMPANY_FIELD


def run_accounts_seed(company: str, seed_version: str) -> dict:
    abbr = frappe.db.get_value("Company", company, "abbr")
    currency = frappe.db.get_value("Company", company, "default_currency") or "BDT"
    created: list[str] = []
    ensure_fiscal_year(company, created)
    warehouse = ensure_default_warehouse(company, abbr, created)
    selling = ensure_price_list(company, f"{company} Selling", currency, selling=True, created=created)
    buying = ensure_price_list(company, f"{company} Buying", currency, selling=False, created=created)
    customer = ensure_walk_in_customer(company, abbr, selling, created)
    supplier = ensure_cash_supplier(company, abbr, created)
    set_company_defaults(company, warehouse)
    created.extend(ensure_office_expense_defaults(company))
    return {
        "company": company,
        "seed_version": seed_version,
        "warehouse": warehouse,
        "selling_price_list": selling,
        "buying_price_list": buying,
        "walk_in_customer": customer,
        "cash_supplier": supplier,
        "created": created,
    }


def ensure_fiscal_year(company: str, created: list[str]) -> str:
    """A fiscal year covering today (calendar year if none exists)."""
    today = getdate(nowdate())
    rows = frappe.get_all(
        "Fiscal Year",
        filters={"year_start_date": ["<=", today], "year_end_date": [">=", today], "disabled": 0},
        fields=["name"],
    )
    for row in rows:
        linked = frappe.get_all("Fiscal Year Company", filters={"parent": row.name}, pluck="company")
        if not linked or company in linked:
            return row.name
    name = str(today.year)
    if frappe.db.exists("Fiscal Year", name):
        name = f"{today.year} ({company})"
    doc = frappe.get_doc(
        {
            "doctype": "Fiscal Year",
            "year": name,
            "year_start_date": f"{today.year}-01-01",
            "year_end_date": f"{today.year}-12-31",
            "companies": [{"company": company}],
        }
    ).insert(ignore_permissions=True)
    created.append(f"Fiscal Year {doc.name}")
    return doc.name


def ensure_default_warehouse(company: str, abbr: str, created: list[str]) -> str:
    """ERPNext creates "Stores - ABBR" with the company; recreate it if missing."""
    name = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0, "warehouse_name": "Stores"})
    if name:
        return name
    name = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name", order_by="creation asc")
    if name:
        return name
    parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")
    doc = frappe.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": "Stores",
            "company": company,
            "parent_warehouse": parent,
        }
    ).insert(ignore_permissions=True)
    created.append(f"Warehouse {doc.name}")
    return doc.name


def ensure_price_list(company: str, title: str, currency: str, *, selling: bool, created: list[str]) -> str:
    name = frappe.db.get_value(
        "Price List",
        {MASTER_COMPANY_FIELD: company, "selling" if selling else "buying": 1, "enabled": 1},
        "name",
        order_by="creation asc",
    )
    if name:
        return name
    price_list_name = title
    suffix = 2
    while frappe.db.exists("Price List", price_list_name):
        price_list_name = f"{title} {suffix}"
        suffix += 1
    doc = frappe.get_doc(
        {
            "doctype": "Price List",
            "price_list_name": price_list_name,
            "currency": currency,
            "selling": 1 if selling else 0,
            "buying": 0 if selling else 1,
            "enabled": 1,
            MASTER_COMPANY_FIELD: company,
        }
    ).insert(ignore_permissions=True)
    created.append(f"Price List {doc.name}")
    return doc.name


def ensure_walk_in_customer(company: str, abbr: str, price_list: str, created: list[str]) -> str:
    name = frappe.db.get_value("Customer", {MASTER_COMPANY_FIELD: company, "customer_name": "Walk-in Customer"})
    if name:
        return name
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": "Walk-in Customer",
            "customer_type": "Individual",
            "customer_group": _leaf("Customer Group"),
            "territory": _leaf("Territory"),
            "default_price_list": price_list,
            MASTER_COMPANY_FIELD: company,
        }
    )
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True, set_name=_unique_name("Customer", f"Walk-in Customer - {abbr}"))
    created.append(f"Customer {doc.name}")
    return doc.name


def ensure_cash_supplier(company: str, abbr: str, created: list[str]) -> str:
    name = frappe.db.get_value("Supplier", {MASTER_COMPANY_FIELD: company, "supplier_name": "Cash Purchase"})
    if name:
        return name
    doc = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": "Cash Purchase",
            "supplier_type": "Individual",
            "supplier_group": _leaf("Supplier Group"),
            MASTER_COMPANY_FIELD: company,
        }
    )
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True, set_name=_unique_name("Supplier", f"Cash Purchase - {abbr}"))
    created.append(f"Supplier {doc.name}")
    return doc.name


def set_company_defaults(company: str, warehouse: str) -> None:
    """Stock-keeping defaults SMEs expect: perpetual inventory with a default store."""
    meta = frappe.get_meta("Company")
    values = {}
    if meta.has_field("enable_perpetual_inventory"):
        values["enable_perpetual_inventory"] = 1
    if meta.has_field("default_warehouse_for_sales_return"):
        values["default_warehouse_for_sales_return"] = warehouse
    for field, value in values.items():
        if frappe.db.get_value("Company", company, field) in (None, "", 0):
            frappe.db.set_value("Company", company, field, value)


def _leaf(doctype: str) -> str | None:
    """A shared (unowned) non-group node, e.g. "Individual" or "All Territories"."""
    filters = {"is_group": 0}
    if frappe.db.has_column(doctype, MASTER_COMPANY_FIELD):
        filters[MASTER_COMPANY_FIELD] = ["is", "not set"]
    return frappe.db.get_value(doctype, filters, "name", order_by="lft asc") or frappe.db.get_value(
        doctype, {"is_group": 0}, "name"
    )


def _unique_name(doctype: str, base: str) -> str:
    name, suffix = base, 2
    while frappe.db.exists(doctype, name):
        name = f"{base} {suffix}"
        suffix += 1
    return name
