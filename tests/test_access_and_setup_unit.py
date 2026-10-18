"""Roles, team access, seed and home page (no database)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from frappe_stub import REPO_ROOT, _Dict, app_modules


class RoleSyncTests(unittest.TestCase):
    def _sync(self, ctx, access, assignments, current_roles, modules=("accounts",)):
        ctx.saas.get_company_module_keys.side_effect = lambda company: list(modules)
        ctx.frappe.db.exists.return_value = True
        ctx.frappe.get_all.side_effect = lambda doctype, **kw: (
            [_Dict(row) for row in assignments] if doctype == "Tenant User Assignment" else []
        )
        ctx.frappe.get_roles.return_value = list(current_roles)
        user = Mock()
        ctx.frappe.get_doc.return_value = user
        access.sync_user("clerk@acme.example")
        return user

    def test_profile_roles_are_added_and_stale_ones_removed(self):
        with app_modules("access") as (ctx, (access,)):
            user = self._sync(
                ctx, access,
                [{"company": "Acme", "role_profile": "Sales User"}],
                ["Reckon Accounts SaaS Stock User", "Stock Manager", "Stock User"],
            )
        removed = set(user.remove_roles.call_args.args)
        added = set(user.add_roles.call_args.args)
        self.assertEqual(removed, {"Reckon Accounts SaaS Stock User", "Stock Manager"})
        self.assertIn("Reckon Accounts SaaS Sales User", added)
        self.assertIn("Sales User", added)
        self.assertNotIn("Stock User", added)  # already held and still wanted

    def test_company_permission_is_created(self):
        with app_modules("access") as (ctx, (access,)):
            self._sync(ctx, access, [{"company": "Acme", "role_profile": "Accountant"}], [])
            values = ctx.frappe.get_doc.call_args_list[-1].args[0]
        self.assertEqual((values["allow"], values["for_value"], values["apply_to_all_doctypes"]), ("Company", "Acme", 1))

    def test_other_module_tenants_are_skipped(self):
        with app_modules("access") as (ctx, (access,)):
            ctx.saas.get_company_module_keys.return_value = ["distribution"]
            ctx.frappe.get_doc.reset_mock()
            access.sync_tenant_user_access(SimpleNamespace(get={"company": "Acme", "user": "dsr@acme.example"}.get))
            ctx.frappe.get_doc.assert_not_called()

    def test_erpnext_roles_kept_when_another_module_also_uses_them(self):
        with app_modules("access") as (ctx, (access,)):
            user = self._sync(
                ctx, access,
                [{"company": "Acme", "role_profile": "Sales User"}, {"company": "Beta", "role_profile": "Company Admin"}],
                ["Stock Manager", "Reckon Accounts SaaS Admin"],
                modules=(),
            )
            # Neither company uses Accounts here, so only Accounts SaaS roles are dropped.
            self.assertEqual(set(user.remove_roles.call_args.args), {"Reckon Accounts SaaS Admin"})


class TeamAccessTests(unittest.TestCase):
    def test_only_company_admin_manages_the_team(self):
        with app_modules("team_access") as (ctx, (team,)):
            ctx.frappe.get_roles.return_value = ["Reckon Accounts SaaS Sales User"]
            with self.assertRaises(ctx.frappe.PermissionError):
                team.get_team()

    def test_existing_login_from_another_tenant_is_never_attached(self):
        with app_modules("team_access") as (ctx, (team,)):
            ctx.frappe.get_roles.return_value = ["Reckon Accounts SaaS Admin"]
            ctx.frappe.db.exists.side_effect = lambda doctype, filters=None: doctype == "User"
            ctx.frappe.get_all.return_value = ["Rival"]
            with self.assertRaises(ctx.frappe.ValidationError):
                team.add_member("boss@rival.example", "Boss", "Accountant")
            ctx.frappe.new_doc.assert_not_called()

    def test_invalid_input_is_refused(self):
        with app_modules("team_access") as (ctx, (team,)):
            ctx.frappe.get_roles.return_value = ["Reckon Accounts SaaS Admin"]
            for args in (("not-an-email", "X", "Accountant"), ("a@acme.example", "", "Accountant"),
                         ("a@acme.example", "A", "System Manager")):
                with self.subTest(args=args), self.assertRaises(ctx.frappe.ValidationError):
                    team.add_member(*args)

    def test_new_member_gets_user_and_assignment(self):
        with app_modules("team_access") as (ctx, (team,)):
            ctx.frappe.get_roles.return_value = ["Reckon Accounts SaaS Admin"]
            ctx.frappe.db.exists.return_value = None
            ctx.frappe.db.get_value.return_value = None
            assignment = _Dict(name="TUA-9")
            assignment.update = lambda values: dict.update(assignment, values)
            assignment.save = Mock()
            ctx.frappe.new_doc.return_value = assignment
            self.assertEqual(team.add_member("New@Acme.example ", "New Clerk", "Sales User"), "TUA-9")
            user_values = ctx.frappe.get_doc.call_args.args[0]
            self.assertEqual((user_values["email"], user_values["send_welcome_email"]), ("new@acme.example", 1))
            self.assertEqual((assignment["company"], assignment["role_profile"], assignment["active"]), ("Acme", "Sales User", 1))

    def test_admin_cannot_lock_themselves_out_or_touch_other_companies(self):
        with app_modules("team_access") as (ctx, (team,)):
            ctx.frappe.get_roles.return_value = ["Reckon Accounts SaaS Admin"]
            ctx.frappe.get_doc.return_value = _Dict(company="Rival", user="x@rival.example")
            with self.assertRaises(ctx.frappe.PermissionError):
                team.update_member("TUA-1", active=0)
            ctx.frappe.get_doc.return_value = _Dict(company="Acme", user="owner@acme.example", role_profile="Company Admin")
            with self.assertRaises(ctx.frappe.ValidationError):
                team.update_member("TUA-2", active=0)
            with self.assertRaises(ctx.frappe.ValidationError):
                team.update_member("TUA-2", role_profile="Sales User")


class SeedTests(unittest.TestCase):
    def test_existing_setup_is_reused_without_inserts(self):
        with app_modules("seed") as (ctx, (seed,)):
            ctx.frappe.db.get_value.side_effect = lambda doctype, filters=None, *a, **k: {
                "Company": "ACM", "Warehouse": "Stores - ACM", "Price List": "Acme Selling",
                "Customer": "Walk-in Customer - ACM", "Supplier": "Cash Purchase - ACM",
            }.get(doctype)
            ctx.frappe.get_all.side_effect = lambda doctype, **kw: [_Dict(name="2026")] if doctype == "Fiscal Year" else []
            ctx.frappe.get_meta.return_value = SimpleNamespace(has_field=lambda f: False)
            result = seed.run_accounts_seed("Acme", "2026.10.06")
        self.assertEqual(result["created"], [])
        self.assertEqual(result["walk_in_customer"], "Walk-in Customer - ACM")
        ctx.frappe.get_doc.assert_not_called()

    def test_fresh_company_gets_price_lists_and_default_parties(self):
        with app_modules("seed") as (ctx, (seed,)):
            def get_value(doctype, filters=None, *args, **kwargs):
                if doctype == "Company":
                    return "ACM" if args == ("abbr",) else "BDT"
                if doctype == "Warehouse":
                    return "Stores - ACM"
                if doctype in {"Customer Group", "Territory", "Supplier Group"}:
                    return "All " + doctype
                return None

            ctx.frappe.db.get_value.side_effect = get_value
            ctx.frappe.db.exists.return_value = None
            ctx.frappe.get_all.side_effect = lambda doctype, **kw: [_Dict(name="2026")] if doctype == "Fiscal Year" else []
            ctx.frappe.get_meta.return_value = SimpleNamespace(has_field=lambda f: False)
            created = []

            def get_doc(values):
                doc = Mock(name=values["doctype"])
                doc.name = values.get("price_list_name") or values.get("customer_name") or values.get("supplier_name")
                doc.insert.return_value = doc
                created.append(values)
                return doc

            ctx.frappe.get_doc.side_effect = get_doc
            result = seed.run_accounts_seed("Acme", "2026.10.06")
        self.assertEqual({v["doctype"] for v in created}, {"Price List", "Customer", "Supplier"})
        self.assertTrue(all(v["rd_company"] == "Acme" for v in created))
        self.assertEqual(len(result["created"]), 4)

    def test_fresh_company_gets_office_expense_settings(self):
        with app_modules("seed") as (ctx, (seed,)):
            ctx.frappe.db.get_value.side_effect = lambda doctype, filters=None, *a, **k: {
                "Company": "ACM", "Warehouse": "Stores - ACM", "Price List": "Acme Selling",
                "Customer": "Walk-in Customer - ACM", "Supplier": "Cash Purchase - ACM",
            }.get(doctype)
            ctx.frappe.get_all.side_effect = lambda doctype, **kw: [_Dict(name="2026")] if doctype == "Fiscal Year" else []
            ctx.frappe.get_meta.return_value = SimpleNamespace(has_field=lambda f: False)
            defaults = ctx.office_expense_setup.ensure_office_expense_defaults
            defaults.return_value = ["Account: Office Rent - ACM", "Office Expense Settings"]
            result = seed.run_accounts_seed("Acme", "2026.10.18")
        defaults.assert_called_once_with("Acme")
        self.assertEqual(result["created"], ["Account: Office Rent - ACM", "Office Expense Settings"])

    def test_office_expense_seed_comes_from_reckon_accounts(self):
        source = (REPO_ROOT / "reckon_accounts_saas" / "seed.py").read_text(encoding="utf-8")
        self.assertIn("from reckon_accounts.office_expense_setup import ensure_office_expense_defaults", source)
        hooks = (REPO_ROOT / "reckon_accounts_saas" / "hooks.py").read_text(encoding="utf-8")
        required = next(line for line in hooks.splitlines() if line.startswith("required_apps"))
        self.assertIn('"reckon_accounts"', required)


class HomeTests(unittest.TestCase):
    def test_tenant_cannot_open_another_company_home(self):
        with app_modules("home") as (ctx, (home,)):
            self.assertEqual(home._resolve_company("Rival"), "Acme")

    def test_vendor_needs_permission_for_the_company(self):
        with app_modules("home") as (ctx, (home,)):
            ctx.tenant_security.user_can_bypass_tenant.return_value = True
            ctx.frappe.has_permission.return_value = False
            with self.assertRaises(ctx.frappe.PermissionError):
                home._resolve_company("Rival")


if __name__ == "__main__":
    unittest.main()
