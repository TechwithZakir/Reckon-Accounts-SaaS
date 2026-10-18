"""Install and migrate: roles, master owner fields, Desk navigation, user repair."""

from __future__ import annotations

import json
from pathlib import Path

import frappe

from reckon_accounts_saas.constants import (
    MASTER_COMPANY_FIELD,
    MASTER_INSERT_AFTER,
    OWNED_MASTERS,
    SAAS_ROLES,
    SHARED_OR_OWNED_MASTERS,
    WORKSPACE_SIDEBAR,
)

MODULE = "Accounts SaaS"
# Frappe looks for the file at <app>/workspace_sidebar/<frappe.scrub(name)>.json.
SIDEBAR_FILE = Path(__file__).parent / "workspace_sidebar" / "accounts_saas.json"


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
    """Frappe v16 left rail for the Accounts SaaS pages, kept in step with the shipped file."""
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
    """The rail shipped in ``workspace_sidebar/accounts_saas.json``, minus links this site lacks.

    The file is the single source of truth. Frappe v16 imports it on migrate, and its orphan
    sweep deletes a standard Workspace Sidebar whose app has no
    ``<app>/workspace_sidebar/<scrubbed name>.json``, so the rail must not live only in code.
    """
    definition = json.loads(SIDEBAR_FILE.read_text(encoding="utf-8"))
    definition.pop("modified", None)
    definition["items"] = [
        item
        for item in definition["items"]
        if item["type"] != "Link" or frappe.db.exists(item["link_type"], item["link_to"])
    ]
    return definition
