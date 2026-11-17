import frappe


def execute():
    """Accounts Dashboard sits right after Home in the Accounts SaaS menu (the menu Desk shows is a Sidebar record)."""
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "Accounts SaaS"):
        return
    doc = frappe.get_doc("Sidebar", "Accounts SaaS")
    rows = list(doc.get("items") or [])
    dash = next((r for r in rows if (r.get("link_to") or "") == "accounts-dashboard"), None)
    home = next((i for i, r in enumerate(rows) if (r.get("link_to") or "") == "accounts-home"), None)
    if dash is None or home is None:
        return
    rows.remove(dash)
    rows.insert(home + 1, dash)
    dash.child = 0
    dash.icon = "layout-dashboard"
    for n, row in enumerate(rows, start=1):
        row.idx = n
    doc.set("items", rows)
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.clear_cache()
