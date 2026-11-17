import frappe


def execute():
    """A Voucher Entry shortcut sits right after Accounts Dashboard in the Accounts SaaS menu (a Sidebar record in Desk)."""
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "Accounts SaaS"):
        return
    doc = frappe.get_doc("Sidebar", "Accounts SaaS")
    rows = list(doc.get("items") or [])
    dash = next((i for i, r in enumerate(rows) if (r.get("link_to") or "") == "accounts-dashboard"), None)
    if dash is None:
        return
    if any((r.get("link_to") or "") == "voucher-entry" and not r.get("child") for r in rows):
        return  # already there at the top level
    doc.append(
        "items",
        {"label": "Voucher Entry", "type": "Link", "link_type": "Page", "link_to": "voucher-entry", "icon": "keyboard", "child": 0, "indent": 0, "collapsible": 1, "show_arrow": 0},
    )
    rows = list(doc.get("items"))
    new = rows.pop()
    rows.insert(dash + 1, new)
    for n, row in enumerate(rows, start=1):
        row.idx = n
    doc.set("items", rows)
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.clear_cache()
