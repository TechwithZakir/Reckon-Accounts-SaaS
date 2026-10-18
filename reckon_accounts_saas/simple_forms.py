"""Lean ERPNext forms for small-business users.

Tenant users see only the fields a small business needs on each form. Mandatory
fields, fields ERPNext marks mandatory while editing, and fields that already
hold a value outside the list stay visible, so nothing required is hidden. The
hiding is client-side and per user (``public/js/simple_form.js``): ERPNext's
meta and other users' forms are not changed. A "Show all fields" button undoes
it for the current form.
"""

from __future__ import annotations

import frappe

from reckon_accounts_saas.desk_guard import get_accounts_scope
from reckon_accounts_saas.form_config import ALWAYS_HIDDEN, ESSENTIAL_FIELDS


def boot_session(bootinfo) -> None:
    """``boot_session`` hook: ship the lean-form lists with the Desk boot."""
    if frappe.session.user in {"Guest", None}:
        return
    try:
        scope = get_accounts_scope()
    except Exception:
        scope = None
    bootinfo.reckon_simple_forms = {
        "enabled": scope is not None,
        "fields": {doctype: list(fields) for doctype, fields in ESSENTIAL_FIELDS.items()},
        "always_hidden": list(ALWAYS_HIDDEN),
    }
