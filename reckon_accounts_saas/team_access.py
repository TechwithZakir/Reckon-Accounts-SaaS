"""Team & Access page API: the company admin adds and manages colleagues."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import validate_email_address

from reckon_accounts_saas.constants import PROFILES, TEAM_MANAGER_ROLES
from reckon_accounts_saas.tenant import tenant_company


@frappe.whitelist()
def get_team() -> dict:
    company = _require_team_manager()
    rows = frappe.get_all(
        "Tenant User Assignment",
        filters={"company": company},
        fields=["name", "user", "role_profile", "active"],
        order_by="active desc, creation asc",
    )
    names = {
        user.name: user.full_name
        for user in frappe.get_all(
            "User", filters={"name": ["in", [r.user for r in rows] or [""]]}, fields=["name", "full_name"]
        )
    }
    return {
        "company": company,
        "profiles": list(PROFILES),
        "members": [
            {
                "assignment": row.name,
                "user": row.user,
                "full_name": names.get(row.user) or row.user,
                "role_profile": row.role_profile,
                "active": bool(row.active),
                "is_self": row.user == frappe.session.user,
            }
            for row in rows
        ],
    }


@frappe.whitelist(methods=["POST"])
def add_member(email: str, full_name: str, role_profile: str) -> str:
    """Create (or invite) a colleague and assign them to the admin's company."""
    company = _require_team_manager()
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    if not validate_email_address(email, throw=False):
        frappe.throw(_("Enter a valid email address."))
    if not full_name:
        frappe.throw(_("Enter the person's name."))
    _validate_profile(role_profile)

    if frappe.db.exists("User", email):
        other = frappe.get_all(
            "Tenant User Assignment",
            filters={"user": email, "company": ["!=", company]},
            pluck="company",
            limit=1,
        )
        if other or not frappe.db.exists("Tenant User Assignment", {"user": email, "company": company}):
            # Never attach an existing login (possibly another tenant's) to this company.
            frappe.throw(_("This email already has an account. Ask them to use a different email."))
    else:
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": full_name,
                "user_type": "System User",
                "send_welcome_email": 1,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    existing = frappe.db.get_value("Tenant User Assignment", {"user": email, "company": company}, "name")
    assignment = frappe.get_doc("Tenant User Assignment", existing) if existing else frappe.new_doc(
        "Tenant User Assignment"
    )
    assignment.update(
        {"user": email, "company": company, "role_profile": role_profile, "active": 1, "is_default": 1}
    )
    assignment.save(ignore_permissions=True)
    return assignment.name


@frappe.whitelist(methods=["POST"])
def update_member(assignment: str, role_profile: str | None = None, active: int | None = None) -> str:
    company = _require_team_manager()
    doc = frappe.get_doc("Tenant User Assignment", assignment)
    if doc.company != company:
        frappe.throw(_("This person is not in your company."), frappe.PermissionError)
    if doc.user == frappe.session.user and (active is not None and not int(active)):
        frappe.throw(_("You cannot deactivate your own access."))
    if doc.user == frappe.session.user and role_profile and role_profile != doc.role_profile:
        frappe.throw(_("Ask another company admin to change your own role."))
    if role_profile:
        _validate_profile(role_profile)
        doc.role_profile = role_profile
    if active is not None:
        doc.active = 1 if int(active) else 0
    doc.save(ignore_permissions=True)
    if not doc.active:
        frappe.db.set_value("User", doc.user, "enabled", 0)
    else:
        frappe.db.set_value("User", doc.user, "enabled", 1)
    return doc.name


def _validate_profile(role_profile: str) -> None:
    if role_profile not in PROFILES:
        frappe.throw(_("Choose a valid role."))


def _require_team_manager() -> str:
    company = tenant_company()
    if company is None:
        frappe.throw(_("Open Team & Access from a tenant account."), frappe.PermissionError)
    if not TEAM_MANAGER_ROLES.intersection(frappe.get_roles()):
        frappe.throw(_("Only the company admin can manage the team."), frappe.PermissionError)
    return company
