"""Desk and API boundary for Accounts tenants (no database)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from frappe_stub import _Dict, app_modules


def _request(ctx, path, **form):
    ctx.frappe.local.request = SimpleNamespace(path=path)
    ctx.frappe.local.form_dict = _Dict(form)


class AccountsScopeTests(unittest.TestCase):
    def test_vendor_and_other_module_tenants_are_not_ours(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.tenant_security.user_can_bypass_tenant.return_value = True
            self.assertIsNone(guard.get_accounts_scope("vendor@reckon.tech"))
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.saas.get_company_module_keys.return_value = ["distribution"]
            self.assertIsNone(guard.get_accounts_scope("dsr@acme.example"))
        with app_modules("desk_guard") as (ctx, (guard,)):
            self.assertEqual(guard.get_accounts_scope("owner@acme.example").company, "Acme")

    def test_multi_module_tenant_gets_the_union(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.saas.get_company_module_keys.return_value = ["accounts", "distribution"]
            ctx.module_registry.get_saas_modules.return_value = [
                _Dict(key="distribution", desk_pages=["field-sales"], desk_doctypes=["DSR Challan"], desk_reports=["DSR Wise Ledger"]),
                _Dict(key="crm", desk_pages=["crm-home"]),
            ]
            scope = guard.get_accounts_scope("owner@acme.example")
        self.assertIn("field-sales", scope.pages)
        self.assertIn("dsr-challan", scope.routes)
        self.assertIn("DSR Wise Ledger", scope.reports)
        self.assertNotIn("crm-home", scope.pages)


class DeskRouteTests(unittest.TestCase):
    def _run(self, path, **form):
        with app_modules("desk_guard") as (ctx, (guard,)):
            _request(ctx, path, **form)
            guard.restrict_accounts_desk_request()
            return ctx.frappe.flags.accounts_saas_redirect

    def test_allowed_routes_pass(self):
        for path in ("/desk/accounts-home", "/app/sales-invoice/new", "/app/item/ITEM-1", "/desk/voucher-entry",
                     "/app/account/view/tree", "/app/query-report/Day Book", "/app/query-report/Stock Balance"):
            with self.subTest(path=path):
                self.assertIsNone(self._run(path))

    def test_root_and_foreign_routes_go_home(self):
        for path in ("/app", "/desk/", "/app/user", "/app/hr-settings", "/app/query-report/Employee Birthday",
                     "/desk/distribution"):
            with self.subTest(path=path):
                self.assertEqual(self._run(path), "/desk/accounts-home")

    def test_website_pages_are_untouched(self):
        self.assertIsNone(self._run("/reckonerp-subscription"))

    def test_gate_blocked_requests_are_left_to_the_gate(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.frappe.flags.saas_gate_blocked = True
            _request(ctx, "/app/hr-settings")
            guard.restrict_accounts_desk_request()
            self.assertIsNone(ctx.frappe.flags.accounts_saas_redirect)


class ApiTests(unittest.TestCase):
    def _call(self, path, owners=None, **form):
        owners = owners or {}
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.frappe.db.get_value.side_effect = lambda doctype, name, field, as_dict=False: (
                {field: owners.get((doctype, name))} if as_dict and (doctype, name) in owners
                else None if as_dict else owners.get((doctype, name))
            )
            _request(ctx, path, **form)
            guard.restrict_accounts_desk_request()
            return ctx.frappe.local.form_dict

    def assertRefused(self, path, owners=None, **form):
        with self.assertRaises(Exception) as raised:
            self._call(path, owners, **form)
        self.assertEqual(type(raised.exception).__name__, "PermissionError")

    def test_resource_api_only_for_allowed_doctypes(self):
        self._call("/api/resource/Sales Invoice")
        self.assertRefused("/api/resource/Salary Slip")
        self.assertRefused("/api/v2/document/Employee/HR-1")

    def test_generic_desk_apis_check_the_doctype(self):
        self._call("/api/method/frappe.client.get_list", doctype="Customer")
        self.assertRefused("/api/method/frappe.client.get_list", doctype="Employee")
        self.assertRefused("/api/method/frappe.desk.reportview.get", args=json.dumps({"doctype": "Salary Slip"}))

    def test_pages_and_reports(self):
        self._call("/api/method/frappe.desk.desk_page.getpage", name="accounts-home")
        self.assertRefused("/api/method/frappe.desk.desk_page.getpage", name="setup-wizard")
        self.assertRefused("/api/method/frappe.desk.query_report.run", report_name="Employee Leave Balance")

    def test_report_company_is_pinned(self):
        form = self._call(
            "/api/method/frappe.desk.query_report.run",
            report_name="General Ledger",
            filters=json.dumps({"company": "Acme", "from_date": "2026-01-01"}),
        )
        self.assertEqual(json.loads(form["filters"])["company"], "Acme")
        self.assertRefused(
            "/api/method/frappe.desk.query_report.run",
            report_name="General Ledger",
            company="Rival",
        )
        form = self._call("/api/method/frappe.desk.query_report.run", report_name="Stock Balance",
                          filters=json.dumps({"warehouse": ""}))
        self.assertEqual(json.loads(form["filters"])["company"], "Acme")

    def test_foreign_records_in_parameters_are_refused(self):
        owners = {("Warehouse", "Stores - R"): "Rival", ("Item", "I-R"): "Rival", ("Customer", "C-R"): "Rival",
                  ("Warehouse", "Stores - A"): "Acme", ("Item", "I-A"): "Acme"}
        self._call("/api/method/erpnext.stock.utils.get_stock_balance", owners, item_code="I-A", warehouse="Stores - A")
        self.assertRefused("/api/method/erpnext.stock.utils.get_stock_balance", owners, item_code="I-A", warehouse="Stores - R")
        self.assertRefused("/api/method/erpnext.stock.get_item_details.get_item_details", owners,
                           args=json.dumps({"item_code": "I-R", "company": "Acme"}))
        self.assertRefused("/api/method/erpnext.accounts.party.get_party_details", owners,
                           party_type="Customer", party="C-R")
        self.assertRefused("/api/method/erpnext.accounts.utils.get_balance_on", owners, company="Rival")
        self.assertRefused("/", owners, cmd="erpnext.accounts.utils.get_balance_on", company="Rival")


class HomeAndRedirectTests(unittest.TestCase):
    def test_redirect_response_but_gate_wins(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            response = Mock(headers={})
            ctx.frappe.flags.accounts_saas_redirect = "/desk/accounts-home"
            guard.redirect_accounts_desk_response(response, None)
            self.assertEqual(response.status_code, 302)
            response = Mock(headers={"Location": "/reckonerp-subscription"})
            ctx.frappe.flags.saas_gate_redirect = "/reckonerp-subscription"
            guard.redirect_accounts_desk_response(response, None)
            self.assertEqual(response.headers["Location"], "/reckonerp-subscription")

    def test_home_page_for_tenant_gated_tenant_and_others(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            self.assertEqual(guard.get_user_home_page("owner@acme.example"), "desk/accounts-home")
            ctx.saas_gate.is_user_gated.return_value = True
            self.assertEqual(guard.get_user_home_page("owner@acme.example"), "reckonerp-subscription")

    def test_other_users_fall_through_to_other_modules(self):
        with app_modules("desk_guard") as (ctx, (guard,)):
            ctx.saas.get_company_module_keys.return_value = ["distribution"]
            ctx.frappe.get_hooks.return_value = [
                "reckon_distribution.desk_guard.get_user_home_page",
                "reckon_accounts_saas.desk_guard.get_user_home_page",
            ]
            ctx.frappe.get_attr.return_value = Mock(return_value="desk/distribution")
            self.assertEqual(guard.get_user_home_page("dsr@acme.example"), "desk/distribution")
            ctx.frappe.get_attr.assert_called_once_with("reckon_distribution.desk_guard.get_user_home_page")


if __name__ == "__main__":
    unittest.main()
