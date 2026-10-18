"""Hooks, module definition, navigation and lean-form configuration stay consistent."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from frappe_stub import REPO_ROOT, app_modules

APP = REPO_ROOT / "reckon_accounts_saas"


class HooksTests(unittest.TestCase):
    def test_every_isolated_doctype_has_query_permission_and_save_hooks(self):
        with app_modules("hooks", "constants") as (_ctx, (hooks, c)):
            for doctype in c.COMPANY_DOCTYPES + c.OWNED_MASTERS + c.SHARED_OR_OWNED_MASTERS:
                with self.subTest(doctype=doctype):
                    self.assertIn(doctype, hooks.permission_query_conditions)
                    self.assertIn(doctype, hooks.has_permission)
                    self.assertIn("before_validate", hooks.doc_events[doctype]) if doctype not in {
                        "GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"} else None
            for doctype in ("Company", "Bin", "User"):
                self.assertIn(doctype, hooks.permission_query_conditions)

    def test_hook_paths_resolve_to_functions(self):
        with app_modules("hooks", "tenant", "desk_guard", "access", "simple_forms", "install", "api", "seed") as (_ctx, mods):
            hooks = mods[0]
            modules = {m.__name__: m for m in mods}
            paths = set(hooks.permission_query_conditions.values()) | set(hooks.has_permission.values())
            paths |= {p for events in hooks.doc_events.values() for p in events.values()}
            paths |= set(hooks.before_request) | set(hooks.after_request)
            paths |= {hooks.get_website_user_home_page, hooks.boot_session, hooks.after_install, hooks.after_migrate,
                      hooks.add_to_apps_screen[0]["has_permission"]}
            for path in sorted(paths):
                module_name, _, function = path.rpartition(".")
                with self.subTest(path=path):
                    self.assertTrue(callable(getattr(modules[module_name], function)))

    def test_hooks_expose_no_stray_public_names(self):
        with app_modules("hooks") as (_ctx, (hooks,)):
            known = {
                "app_name", "app_title", "app_publisher", "app_description", "app_email", "app_license",
                "app_logo_url", "app_icon_url", "app_icon_title", "app_icon_route", "required_apps",
                "add_to_apps_screen", "after_install", "after_migrate", "reckon_saas_modules", "before_request",
                "after_request", "get_website_user_home_page", "boot_session", "permission_query_conditions",
                "has_permission", "doc_events", "doctype_js", "fixtures",
            }
            public = {name for name in vars(hooks) if not name.startswith("_") and name != "annotations"}
            self.assertEqual(public - known, set())

    def test_requires_platform_and_reckon_accounts(self):
        with app_modules("hooks") as (_ctx, (hooks,)):
            self.assertTrue({"erpnext", "reckon_saas_platform", "reckon_accounts"} <= set(hooks.required_apps))


class ModuleDefinitionTests(unittest.TestCase):
    def test_definition_matches_platform_contract(self):
        with app_modules("saas_module", "constants") as (_ctx, (module, c)):
            definition = module.get_module_definition()
        self.assertEqual(definition["key"], "accounts")
        self.assertEqual(definition["admin_role"], "Reckon Accounts SaaS Admin")
        self.assertEqual(definition["seed_handler"], "reckon_accounts_saas.seed.run_accounts_seed")
        self.assertIn("accounts-home", definition["desk_pages"])
        self.assertIn("Sales Invoice", definition["desk_doctypes"])
        self.assertIn("Profit and Loss Statement", definition["desk_reports"])
        self.assertTrue(definition["description"])

    def test_every_profile_has_its_saas_role(self):
        with app_modules("constants") as (_ctx, (c,)):
            for profile, roles in c.PROFILE_ROLES.items():
                self.assertIn(roles[0], c.SAAS_ROLES, profile)
            self.assertNotIn("System Manager", c.MANAGED_ROLES)
            self.assertNotIn("Reckon Vendor Superuser", c.MANAGED_ROLES)

    def test_platform_assignment_offers_every_profile(self):
        platform = REPO_ROOT.parent / "Reckon SaaS Platform"
        path = platform / "reckon_saas_platform/saas_platform/doctype/tenant_user_assignment/tenant_user_assignment.json"
        if not path.exists():
            self.skipTest("platform checkout not next to this repository")
        options = next(f["options"] for f in json.loads(path.read_text(encoding="utf-8"))["fields"]
                       if f["fieldname"] == "role_profile").split("\n")
        with app_modules("constants") as (_ctx, (c,)):
            self.assertEqual(set(c.PROFILES) - set(options), set())


class NavigationTests(unittest.TestCase):
    def test_sidebar_only_points_at_reachable_things(self):
        with app_modules("install", "constants") as (ctx, (install, c)):
            ctx.frappe.db.exists.return_value = True
            sidebar = install.workspace_sidebar_doc()
        for item in sidebar["items"]:
            if item["type"] != "Link":
                continue
            with self.subTest(item=item["label"]):
                if item["link_type"] == "DocType":
                    self.assertIn(item["link_to"], c.ALLOWED_DOCTYPES)
                    self.assertNotIn(item["link_to"], c.LOOKUP_ONLY_DOCTYPES)
                elif item["link_type"] == "Report":
                    self.assertIn(item["link_to"], c.ALLOWED_REPORTS)
                else:
                    self.assertIn(item["link_to"], c.ALLOWED_PAGES)
        self.assertEqual(sidebar["items"][0]["link_to"], "accounts-home")

    def test_pages_exist_with_matching_roles(self):
        for page, roles in (("accounts_home", "Reckon Accounts SaaS Sales User"), ("accounts_team", "Reckon Accounts SaaS Admin")):
            data = json.loads((APP / "accounts_saas/page" / page / f"{page}.json").read_text(encoding="utf-8"))
            self.assertEqual(data["module"], "Accounts SaaS")
            self.assertIn(roles, {r["role"] for r in data["roles"]})
            self.assertTrue((APP / "accounts_saas/page" / page / f"{page}.js").exists())

    def test_home_page_quick_links_are_reachable(self):
        js = (APP / "accounts_saas/page/accounts_home/accounts_home.js").read_text(encoding="utf-8")
        with app_modules("constants") as (_ctx, (c,)):
            for report in ("Day Book", "Cash Book", "Stock Balance", "Accounts Receivable", "Profit and Loss Statement"):
                self.assertIn(report, js)
                self.assertIn(report, c.ALLOWED_REPORTS)


class OfficeExpenseTests(unittest.TestCase):
    """Reckon Accounts' Office Expense is tenant-scoped and one click away."""

    def test_office_expense_documents_are_tenant_isolated(self):
        with app_modules("hooks", "constants") as (_ctx, (hooks, c)):
            for doctype in ("Office Expense", "Office Expense Settings"):
                with self.subTest(doctype=doctype):
                    self.assertIn(doctype, c.COMPANY_DOCTYPES)
                    self.assertEqual(
                        hooks.doc_events[doctype]["before_validate"],
                        "reckon_accounts_saas.tenant.bind_company_document",
                    )
                    self.assertIn(doctype, hooks.permission_query_conditions)
                    self.assertIn(doctype, hooks.has_permission)
            for child in ("Office Expense Item", "Office Expense Category Setup", "Office Expense Payment Setup"):
                self.assertIn(child, c.CHILD_DOCTYPES)
                self.assertIn(child, c.LOOKUP_ONLY_DOCTYPES)

    def test_left_menu_links_the_form_and_its_setup(self):
        with app_modules("install") as (ctx, (install,)):
            ctx.frappe.db.exists.return_value = True
            items = install.workspace_sidebar_doc()["items"]
        links = [(item["label"], item["link_to"]) for item in items if item["type"] == "Link"]
        self.assertIn(("Office Expenses", "Office Expense"), links)
        self.assertIn(("Office Expense Setup", "Office Expense Settings"), links)
        sections = [item["label"] for item in items if item["type"] != "Link"]
        money = links.index(("Payments", "Payment Entry"))
        self.assertLess(money, links.index(("Office Expenses", "Office Expense")))
        self.assertIn("Money", sections)

    def test_left_menu_hides_links_when_reckon_accounts_lacks_the_doctype(self):
        with app_modules("install") as (ctx, (install,)):
            ctx.frappe.db.exists.side_effect = lambda doctype, name=None: not str(name).startswith("Office Expense")
            items = install.workspace_sidebar_doc()["items"]
        self.assertFalse([item for item in items if str(item.get("link_to", "")).startswith("Office Expense")])

    def test_home_page_has_an_office_expense_action(self):
        js = (APP / "accounts_saas/page/accounts_home/accounts_home.js").read_text(encoding="utf-8")
        self.assertIn('frappe.new_doc("Office Expense")', js)


class LeanFormTests(unittest.TestCase):
    def test_lean_forms_cover_reachable_doctypes_only(self):
        with app_modules("form_config", "constants") as (_ctx, (forms, c)):
            for doctype, fields in forms.ESSENTIAL_FIELDS.items():
                with self.subTest(doctype=doctype):
                    self.assertIn(doctype, c.ALLOWED_DOCTYPES)
                    self.assertEqual(len(fields), len(set(fields)), "duplicate field")
            self.assertIn("company", forms.ALWAYS_HIDDEN)

    def test_boot_flags_tenants_only(self):
        with app_modules("simple_forms") as (ctx, (forms,)):
            boot = SimpleNamespace()
            forms.boot_session(boot)
            self.assertTrue(boot.reckon_simple_forms["enabled"])
            self.assertIn("Sales Invoice", boot.reckon_simple_forms["fields"])
            ctx.tenant_security.user_can_bypass_tenant.return_value = True
            boot = SimpleNamespace()
            forms.boot_session(boot)
            self.assertFalse(boot.reckon_simple_forms["enabled"])

    def test_form_script_registered_for_every_lean_doctype(self):
        with app_modules("hooks", "form_config") as (_ctx, (hooks, forms)):
            self.assertEqual(set(hooks.doctype_js), set(forms.ESSENTIAL_FIELDS))
        self.assertTrue(Path(APP / "public/js/simple_form.js").exists())


if __name__ == "__main__":
    unittest.main()
