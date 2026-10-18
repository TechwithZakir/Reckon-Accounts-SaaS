"""Install and migrate: roles, master owner fields, Desk navigation, user repair."""

from __future__ import annotations

import frappe

from reckon_accounts_saas.constants import (
    HOME_PAGE,
    MASTER_COMPANY_FIELD,
    MASTER_INSERT_AFTER,
    OWNED_MASTERS,
    SAAS_ROLES,
    SHARED_OR_OWNED_MASTERS,
    TEAM_PAGE,
    WORKSPACE_SIDEBAR,
)

MODULE = "Accounts SaaS"


def after_install() -> None:
    after_migrate()


def after_migrate() -> None:
    setup_roles()
    ensure_master_owner_fields()
    backfill_contact_owners()
    ensure_workspace_sidebar()
    from reckon_accounts_saas.access import backfill_accounts_users

    backfill_accounts_users()


def setup_roles() -> None:
    for role in SAAS_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1, "is_custom": 1}
            ).insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Role", role, {"desk_access": 1, "home_page": ""})


def ensure_master_owner_fields() -> None:
    """Add the shared ``rd_company`` owner field to masters without a company.

    Reckon Distribution installs the same field on Customer, Supplier, Item,
    Price List and Item Price; whichever app runs first creates it.
    """
    for doctype in OWNED_MASTERS + SHARED_OR_OWNED_MASTERS:
        if not frappe.db.exists("DocType", doctype):
            continue
        if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": MASTER_COMPANY_FIELD}):
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": doctype,
                    "fieldname": MASTER_COMPANY_FIELD,
                    "label": "Company",
                    "fieldtype": "Link",
                    "options": "Company",
                    "read_only": 1,
                    "in_standard_filter": 1,
                    "search_index": 1,
                    "insert_after": MASTER_INSERT_AFTER.get(doctype),
                }
            ).insert(ignore_permissions=True)
            frappe.clear_cache(doctype=doctype)


def backfill_contact_owners() -> None:
    """Give unowned Addresses and Contacts the owner of the party they belong to."""
    for doctype in ("Address", "Contact"):
        if not frappe.db.has_column(doctype, MASTER_COMPANY_FIELD):
            continue
        rows = frappe.get_all(
            "Dynamic Link",
            filters={"parenttype": doctype, "link_doctype": ["in", ["Customer", "Supplier"]]},
            fields=["parent", "link_doctype", "link_name"],
        )
        for row in rows:
            if frappe.db.get_value(doctype, row.parent, MASTER_COMPANY_FIELD):
                continue
            owner = frappe.db.get_value(row.link_doctype, row.link_name, MASTER_COMPANY_FIELD)
            if owner:
                frappe.db.set_value(doctype, row.parent, MASTER_COMPANY_FIELD, owner, update_modified=False)


def ensure_workspace_sidebar() -> None:
    """Frappe v16 left rail for the Accounts SaaS pages (rebuilt every migrate)."""
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return
    definition = workspace_sidebar_doc()
    if frappe.db.exists("Workspace Sidebar", WORKSPACE_SIDEBAR):
        sidebar = frappe.get_doc("Workspace Sidebar", WORKSPACE_SIDEBAR)
        sidebar.set("items", definition["items"])
        sidebar.header_icon = definition["header_icon"]
        sidebar.save(ignore_permissions=True)
    else:
        frappe.get_doc(definition).insert(ignore_permissions=True, ignore_links=True)


def workspace_sidebar_doc() -> dict:
    def section(label, icon):
        return {"type": "Section Break", "label": label, "icon": icon, "child": 0, "indent": 0,
                "collapsible": 1, "keep_closed": 0, "show_arrow": 0}

    def link(label, link_to, link_type, icon, child=True):
        return {"type": "Link", "label": label, "link_to": link_to, "link_type": link_type, "icon": icon,
                "child": int(child), "indent": 0, "collapsible": 1, "show_arrow": 0}

    items = [
        link("Home", HOME_PAGE, "Page", "house", child=False),
        section("Sales", "shopping-cart"),
        link("Sales Invoices", "Sales Invoice", "DocType", "receipt-text"),
        link("Quotations", "Quotation", "DocType", "file-text"),
        link("Sales Orders", "Sales Order", "DocType", "clipboard-list"),
        link("Delivery Notes", "Delivery Note", "DocType", "truck"),
        link("Customers", "Customer", "DocType", "users"),
        section("Purchase", "package-plus"),
        link("Purchase Bills", "Purchase Invoice", "DocType", "file-text"),
        link("Purchase Orders", "Purchase Order", "DocType", "clipboard-list"),
        link("Goods Received", "Purchase Receipt", "DocType", "package-check"),
        link("Suppliers", "Supplier", "DocType", "contact-round"),
        section("Money", "wallet-cards"),
        link("Payments", "Payment Entry", "DocType", "landmark"),
        link("Voucher Entry", "voucher-entry", "Page", "keyboard"),
        link("Office Expenses", "Office Expense", "DocType", "wallet"),
        link("Journal Entries", "Journal Entry", "DocType", "book-open"),
        link("Chart of Accounts", "Account", "DocType", "list-tree"),
        section("Stock", "boxes"),
        link("Items", "Item", "DocType", "package"),
        link("Stock Entries", "Stock Entry", "DocType", "arrow-left-right"),
        link("Stock Count", "Stock Reconciliation", "DocType", "clipboard-check"),
        link("Warehouses", "Warehouse", "DocType", "warehouse"),
        link("Stock Balance", "Stock Balance", "Report", "chart-column"),
        section("Reports", "chart-no-axes-combined"),
        link("Accounts Dashboard", "accounts-dashboard", "Page", "layout-dashboard"),
        link("Day Book", "Day Book", "Report", "book-open-check"),
        link("Cash Book", "Cash Book", "Report", "wallet-cards"),
        link("Party Ledger", "Party Ledger", "Report", "contact-round"),
        link("Accounts Receivable", "Accounts Receivable", "Report", "arrow-down-to-line"),
        link("Accounts Payable", "Accounts Payable", "Report", "arrow-up-from-line"),
        link("Sales Register", "Sales Register", "Report", "receipt-text"),
        link("Purchase Register", "Purchase Register", "Report", "clipboard-list"),
        link("Gross Profit", "Gross Profit", "Report", "trending-up"),
        link("Profit and Loss", "Profit and Loss Statement", "Report", "chart-no-axes-combined"),
        link("Balance Sheet", "Balance Sheet", "Report", "scale"),
        link("Trial Balance", "Trial Balance", "Report", "list-checks"),
        section("Setup", "settings"),
        link("Team & Access", TEAM_PAGE, "Page", "users-round"),
        link("Office Expense Setup", "Office Expense Settings", "DocType", "wallet-cards"),
        link("Price Lists", "Price List", "DocType", "tags"),
        link("Sales Tax Templates", "Sales Taxes and Charges Template", "DocType", "percent"),
        link("Purchase Tax Templates", "Purchase Taxes and Charges Template", "DocType", "percent"),
        link("Company", "Company", "DocType", "building-2"),
    ]
    items = [
        item
        for item in items
        if item["type"] != "Link" or frappe.db.exists(item["link_type"], item["link_to"])
    ]
    return {
        "doctype": "Workspace Sidebar",
        "name": WORKSPACE_SIDEBAR,
        "title": WORKSPACE_SIDEBAR,
        "app": "reckon_accounts_saas",
        "module": MODULE,
        "header_icon": "accounting",
        "standard": 1,
        "items": items,
    }
