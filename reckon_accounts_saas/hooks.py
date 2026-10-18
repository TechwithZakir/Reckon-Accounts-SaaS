"""Reckon Accounts SaaS: one-company-per-tenant accounting on Reckon SaaS Platform.

ERPNext stays the accounting and stock engine and Reckon Accounts provides the
Tally-style books. This app adds tenant isolation, the SaaS module
registration, a small-business home page, team access and lean forms.
"""

# Private aliases: Frappe reads every public name in hooks.py as a hook.
from reckon_accounts_saas import constants as _c
from reckon_accounts_saas import form_config as _forms

app_name = "reckon_accounts_saas"
app_title = "Reckon Accounts SaaS"
app_publisher = "Reckon Technologies Ltd."
app_description = "Single-company SaaS accounting, sales, purchase and stock on ERPNext"
app_email = "hello@reckon.tech"
app_license = "MIT"
app_logo_url = "/assets/reckon_accounts_saas/images/reckon-accounts-saas-icon.svg"
app_icon_url = app_logo_url
app_icon_title = "Accounts"
app_icon_route = _c.HOME_ROUTE

required_apps = ["frappe", "erpnext", "reckon_saas_platform", "reckon_accounts"]

add_to_apps_screen = [
    {
        "name": app_name,
        "logo": app_logo_url,
        "title": "Accounts",
        "route": app_icon_route,
        "desk_route": app_icon_route,
        "has_permission": "reckon_accounts_saas.api.check_app_permission",
        "sequence_id": 15,
    }
]

after_install = "reckon_accounts_saas.install.after_install"
after_migrate = "reckon_accounts_saas.install.after_migrate"

reckon_saas_modules = ["reckon_accounts_saas.saas_module.get_module_definition"]

before_request = ["reckon_accounts_saas.desk_guard.restrict_accounts_desk_request"]
after_request = ["reckon_accounts_saas.desk_guard.redirect_accounts_desk_response"]
get_website_user_home_page = "reckon_accounts_saas.desk_guard.get_user_home_page"
boot_session = "reckon_accounts_saas.simple_forms.boot_session"

_TENANT = "reckon_accounts_saas.tenant"

permission_query_conditions = {
    **{doctype: f"{_TENANT}.get_company_document_query" for doctype in _c.COMPANY_DOCTYPES},
    **{doctype: f"{_TENANT}.get_owned_master_query" for doctype in _c.OWNED_MASTERS + _c.SHARED_OR_OWNED_MASTERS},
    "Company": f"{_TENANT}.get_company_query",
    "Bin": f"{_TENANT}.get_bin_query",
    "User": f"{_TENANT}.get_user_query",
}

has_permission = {
    **{doctype: f"{_TENANT}.has_company_document_permission" for doctype in _c.COMPANY_DOCTYPES},
    **{doctype: f"{_TENANT}.has_owned_master_permission" for doctype in _c.OWNED_MASTERS + _c.SHARED_OR_OWNED_MASTERS},
    "Company": f"{_TENANT}.has_company_permission",
    "Bin": f"{_TENANT}.has_bin_permission",
    "User": f"{_TENANT}.has_user_permission",
}

# Ledgers (GL, Stock Ledger, Payment Ledger) and Bin are written by ERPNext
# itself; only user-entered documents and masters are bound and checked on save.
_LEDGERS = {"GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"}
doc_events = {
    **{
        doctype: {
            "before_validate": f"{_TENANT}.bind_company_document",
            "validate": f"{_TENANT}.validate_company_document",
        }
        for doctype in _c.COMPANY_DOCTYPES
        if doctype not in _LEDGERS
    },
    **{
        doctype: {"before_validate": f"{_TENANT}.bind_owned_master"}
        for doctype in _c.OWNED_MASTERS + _c.SHARED_OR_OWNED_MASTERS
    },
    "Tenant User Assignment": {
        "on_update": "reckon_accounts_saas.access.sync_tenant_user_access",
    },
}

doctype_js = {doctype: "public/js/simple_form.js" for doctype in _forms.ESSENTIAL_FIELDS}

fixtures = [{"dt": "Role", "filters": [["name", "in", list(_c.SAAS_ROLES)]]}]
