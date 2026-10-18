from __future__ import annotations

from reckon_accounts_saas.constants import (
    ADMIN_ROLE,
    ALLOWED_DOCTYPES,
    ALLOWED_PAGES,
    ALLOWED_REPORTS,
    HOME_PAGE,
    HOME_ROUTE,
    MODULE_KEY,
    SAAS_ROLES,
)


def get_module_definition() -> dict:
    """Registration with Reckon SaaS Platform (``reckon_saas_modules`` hook)."""
    return {
        "key": MODULE_KEY,
        "label": "Accounts",
        "description": "Sales, purchase, stock and accounting for any small business: invoices, "
        "bills, payments, inventory and Tally-style books in Bangla and English.",
        "workspace": f"app/{HOME_PAGE}",
        "home_route": HOME_ROUTE,
        "admin_role": ADMIN_ROLE,
        "roles": list(SAAS_ROLES),
        "seed_handler": "reckon_accounts_saas.seed.run_accounts_seed",
        "subscription_features": [
            "sales_invoices_and_quotations",
            "purchase_bills_and_orders",
            "stock_and_warehouses",
            "cash_bank_and_payments",
            "tally_style_books_and_reports",
            "team_roles_for_sales_purchase_stock",
        ],
        "desk_pages": sorted(ALLOWED_PAGES),
        "desk_doctypes": sorted(ALLOWED_DOCTYPES),
        "desk_reports": sorted(ALLOWED_REPORTS),
    }
