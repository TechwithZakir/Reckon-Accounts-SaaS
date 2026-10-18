"""Single source of truth for the Accounts SaaS module: roles, profiles and reach.

One tenant = one Company. Everything a tenant user can open in Desk or through
the API is listed here; anything else stays behind the Desk guard.
"""

from __future__ import annotations

MODULE_KEY = "accounts"
MODULE_NAME = "Accounts SaaS"
HOME_PAGE = "accounts-home"
TEAM_PAGE = "accounts-team"
HOME_ROUTE = f"/desk/{HOME_PAGE}"
WORKSPACE_SIDEBAR = "Accounts SaaS"

ADMIN_ROLE = "Reckon Accounts SaaS Admin"
MANAGER_ROLE = "Reckon Accounts SaaS Manager"
ACCOUNTANT_ROLE = "Reckon Accounts SaaS Accountant"
SALES_ROLE = "Reckon Accounts SaaS Sales User"
PURCHASE_ROLE = "Reckon Accounts SaaS Purchase User"
STOCK_ROLE = "Reckon Accounts SaaS Stock User"
SAAS_ROLES = (ADMIN_ROLE, MANAGER_ROLE, ACCOUNTANT_ROLE, SALES_ROLE, PURCHASE_ROLE, STOCK_ROLE)
TEAM_MANAGER_ROLES = frozenset({ADMIN_ROLE})

# ERPNext and Reckon Accounts roles carry the document permissions; tenant
# isolation comes from this app's query/permission hooks, not from roles.
_ERP_ALL = (
    "Accounts Manager",
    "Accounts User",
    "Sales Manager",
    "Sales User",
    "Purchase Manager",
    "Purchase User",
    "Stock Manager",
    "Stock User",
    "Item Manager",
    "Reckon Accounts Manager",
    "Reckon Accounts User",
)
PROFILE_ROLES: dict[str, tuple[str, ...]] = {
    "Company Admin": (ADMIN_ROLE, *_ERP_ALL),
    "Company Manager": (MANAGER_ROLE, *_ERP_ALL),
    "Accountant": (
        ACCOUNTANT_ROLE,
        "Accounts Manager",
        "Accounts User",
        "Reckon Accounts Manager",
        "Reckon Accounts User",
    ),
    "Sales User": (SALES_ROLE, "Sales User", "Accounts User", "Stock User", "Reckon Accounts User"),
    "Purchase User": (
        PURCHASE_ROLE,
        "Purchase User",
        "Accounts User",
        "Stock User",
        "Reckon Accounts User",
    ),
    "Stock User": (STOCK_ROLE, "Stock User", "Stock Manager", "Item Manager"),
}
PROFILES = tuple(PROFILE_ROLES)
MANAGED_ROLES = frozenset(role for roles in PROFILE_ROLES.values() for role in roles)

# Documents with a native ``company`` field.
COMPANY_DOCTYPES = (
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "Material Request",
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
    "Journal Entry",
    "Landed Cost Voucher",
    "Period Closing Voucher",
    "GL Entry",
    "Payment Ledger Entry",
    "Stock Entry",
    "Stock Reconciliation",
    "Stock Ledger Entry",
    "Serial No",
    "Warehouse",
    "Account",
    "Cost Center",
    "Bank Account",
    "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
    "Item Tax Template",
    # Reckon Accounts' compact expense form and its per-company setup.
    "Office Expense",
    "Office Expense Settings",
)

# ERPNext masters without a company field get the shared ``rd_company`` owner
# field (the same field Reckon Distribution uses, so both modules agree).
MASTER_COMPANY_FIELD = "rd_company"
OWNED_MASTERS = ("Customer", "Supplier", "Item", "Price List", "Item Price", "Address", "Contact")
# Shared taxonomies: rows without an owner are visible to every tenant; rows a
# tenant creates are its own.
SHARED_OR_OWNED_MASTERS = ("Item Group", "Brand", "Customer Group", "Supplier Group", "Territory", "Sales Person")
MASTER_INSERT_AFTER = {
    "Customer": "customer_name",
    "Supplier": "supplier_name",
    "Item": "item_name",
    "Price List": "price_list_name",
    "Item Price": "item_code",
    "Address": "address_title",
    "Contact": "first_name",
    "Item Group": "item_group_name",
    "Brand": "brand",
    "Customer Group": "customer_group_name",
    "Supplier Group": "supplier_group_name",
    "Territory": "territory_name",
    "Sales Person": "sales_person_name",
}

# Read-only or harmless global records forms need.
GLOBAL_DOCTYPES = (
    "Company",
    "UOM",
    "UOM Conversion Factor",
    "Currency",
    "Country",
    "Mode of Payment",
    "Payment Terms Template",
    "Fiscal Year",
    "Print Format",
    "Letter Head",
    "Terms and Conditions",
    "Language",
    "DocType",
    "Report",
    "List Filter",
    "User",
    "Stock Entry Type",
    "Bin",
)

CHILD_DOCTYPES = (
    "Quotation Item",
    "Sales Order Item",
    "Delivery Note Item",
    "Sales Invoice Item",
    "Sales Invoice Payment",
    "Sales Taxes and Charges",
    "Payment Schedule",
    "Material Request Item",
    "Supplier Quotation Item",
    "Purchase Order Item",
    "Purchase Receipt Item",
    "Purchase Invoice Item",
    "Purchase Taxes and Charges",
    "Payment Entry Reference",
    "Payment Entry Deduction",
    "Journal Entry Account",
    "Stock Entry Detail",
    "Stock Reconciliation Item",
    "Landed Cost Item",
    "Landed Cost Taxes and Charges",
    "Landed Cost Purchase Receipt",
    "UOM Conversion Detail",
    "Item Default",
    "Item Barcode",
    "Item Tax Template Detail",
    "Dynamic Link",
    "Office Expense Item",
    "Office Expense Category Setup",
    "Office Expense Payment Setup",
)

ALLOWED_DOCTYPES = frozenset(
    COMPANY_DOCTYPES + OWNED_MASTERS + SHARED_OR_OWNED_MASTERS + GLOBAL_DOCTYPES + CHILD_DOCTYPES
)
# Reachable through the API (forms, link fields, metadata) but not as Desk pages.
LOOKUP_ONLY_DOCTYPES = frozenset(
    {"DocType", "Report", "List Filter", "Language", "User", "Bin", "Letter Head", "Print Format", "Currency", "Country"}
    | set(CHILD_DOCTYPES)
)

RECKON_ACCOUNTS_PAGES = ("accounts-dashboard", "voucher-entry")
ALLOWED_PAGES = frozenset(
    {HOME_PAGE, TEAM_PAGE, *RECKON_ACCOUNTS_PAGES, "query-report", "print", "user-profile", "home"}
)

RECKON_ACCOUNTS_REPORTS = (
    "Party Ledger",
    "Account Ledger",
    "Account Head Wise Party Ledger",
    "Party Summary",
    "General Ledger Custom",
    "Ledger Monthly Summary",
    "Cash Book",
    "Bank Book",
    "Cash Bank Summary",
    "Bank Summary",
    "Receipts and Payments",
    "Group Summary",
    "Group Monthly Summary",
    "Group Vouchers",
    "Funds Flow",
    "Negative Cash",
    "Ledger Exceptions",
    "Day Book",
    "Receipt Register",
    "Payment Register",
    "Contra Register",
    "Journal Register",
    "Debit Note Register",
    "Credit Note Register",
    "Voucher Statistics",
)
ERPNEXT_REPORTS = (
    "General Ledger",
    "Trial Balance",
    "Trial Balance for Party",
    "Balance Sheet",
    "Profit and Loss Statement",
    "Cash Flow",
    "Financial Ratios",
    "Accounts Receivable",
    "Accounts Receivable Summary",
    "Accounts Payable",
    "Accounts Payable Summary",
    "Customer Ledger Summary",
    "Supplier Ledger Summary",
    "Sales Register",
    "Purchase Register",
    "Item-wise Sales Register",
    "Item-wise Purchase Register",
    "Gross Profit",
    "Sales Analytics",
    "Purchase Analytics",
    "Stock Balance",
    "Stock Ledger",
    "Stock Projected Qty",
    "Stock Ageing",
    "Bank Reconciliation Statement",
)
ALLOWED_REPORTS = frozenset(RECKON_ACCOUNTS_REPORTS + ERPNEXT_REPORTS)

# Request parameters that name a company-scoped record. API calls that pass a
# record of another tenant are refused before the method runs.
SCOPED_PARAMETERS = {
    "company": "Company",
    "warehouse": "Warehouse",
    "set_warehouse": "Warehouse",
    "account": "Account",
    "cost_center": "Cost Center",
    "customer": "Customer",
    "supplier": "Supplier",
    "item_code": "Item",
    "price_list": "Price List",
}
