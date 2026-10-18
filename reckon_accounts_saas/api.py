from __future__ import annotations

import frappe

from reckon_accounts_saas.constants import SAAS_ROLES


@frappe.whitelist()
def check_app_permission() -> bool:
    """Show the Accounts SaaS desktop icon to its tenant users and to vendors."""
    user = frappe.session.user
    if user == "Guest":
        return False
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    return bool(roles.intersection({*SAAS_ROLES, "Reckon Vendor Superuser", "System Manager"}))
