"""Bench integration tests: two Accounts tenants on one site must not see each other.

Run on a dedicated test site with ``scripts/test_release_gate.sh --site <site>``.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from reckon_accounts_saas import desk_guard, seed, team_access, tenant
from reckon_accounts_saas.constants import ADMIN_ROLE, MASTER_COMPANY_FIELD, MODULE_KEY


class TestAccountsTenantIsolation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=6).lower()
        self.token = token
        self.company_a = f"_RAS A {token}"
        self.company_b = f"_RAS B {token}"
        self.user_a = f"ras-a-{token}@example.com"
        self.user_b = f"ras-b-{token}@example.com"
        self.cleanup: list[tuple[str, str]] = []
        self.plan = self._plan()
        for company, user in ((self.company_a, self.user_a), (self.company_b, self.user_b)):
            self._company(company)
            self._subscription(company)
            self._user(user)
            self._assign(user, company, "Company Admin")

    def tearDown(self):
        frappe.set_user("Administrator")
        users = [self.user_a, self.user_b] + [n for d, n in self.cleanup if d == "User"]
        for name in frappe.get_all("Tenant User Assignment", filters={"user": ["in", users]}, pluck="name"):
            self._delete("Tenant User Assignment", name)
        for name in frappe.get_all("User Permission", filters={"user": ["in", users]}, pluck="name"):
            self._delete("User Permission", name)
        for doctype in ("Customer", "Supplier", "Item", "Price List", "Warehouse"):
            for name in frappe.get_all(doctype, filters={
                MASTER_COMPANY_FIELD if doctype != "Warehouse" else "company": ["in", [self.company_a, self.company_b]]
            }, pluck="name"):
                self._delete(doctype, name)
        for doctype, name in reversed(self.cleanup):
            self._delete(doctype, name)
        for user in (self.user_a, self.user_b):
            self._delete("User", user)
        for company in (self.company_a, self.company_b):
            for name in frappe.get_all("SaaS Subscription", filters={"company": company}, pluck="name"):
                self._delete("SaaS Subscription", name)
            self._delete("Company", company)
        self._delete("SaaS Plan", self.plan)
        super().tearDown()

    # fixtures ------------------------------------------------------------

    def _plan(self):
        name = f"_RAS Plan {self.token}"
        frappe.get_doc({"doctype": "SaaS Plan", "plan_name": name, "plan_version": "t", "enabled": 1,
                        "currency": "BDT", "price": 1, "billing_cycle": "Monthly",
                        "saas_module": MODULE_KEY}).insert(ignore_permissions=True)
        return name

    def _company(self, company):
        with patch("erpnext.setup.doctype.company.company.Company.on_update"):
            frappe.get_doc({"doctype": "Company", "company_name": company,
                            "abbr": f"R{frappe.generate_hash(length=4).upper()}",
                            "default_currency": "BDT", "country": "Bangladesh"}).insert(ignore_permissions=True)

    def _subscription(self, company):
        frappe.get_doc({"doctype": "SaaS Subscription", "company": company, "plan": self.plan, "plan_version": "t",
                        "status": "Active", "price": 1, "currency": "BDT", "start_date": nowdate(),
                        "end_date": add_days(nowdate(), 30)}).insert(ignore_permissions=True)

    def _user(self, email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "RAS", "send_welcome_email": 0,
                        "enabled": 1}).insert(ignore_permissions=True)

    def _assign(self, user, company, profile):
        frappe.get_doc({"doctype": "Tenant User Assignment", "user": user, "company": company,
                        "role_profile": profile, "active": 1, "is_default": 1}).insert(ignore_permissions=True)

    @contextmanager
    def _as(self, user):
        previous = frappe.session.user
        frappe.set_user(user)
        try:
            yield
        finally:
            frappe.set_user(previous)

    @staticmethod
    def _delete(doctype, name):
        if name and frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

    # tests ---------------------------------------------------------------

    def test_assignment_grants_profile_roles_and_company_permission(self):
        roles = set(frappe.get_roles(self.user_a))
        self.assertIn(ADMIN_ROLE, roles)
        self.assertTrue({"Accounts User", "Sales User", "Stock User"} <= roles)
        self.assertEqual(
            frappe.get_all("User Permission", filters={"user": self.user_a, "allow": "Company"}, pluck="for_value"),
            [self.company_a],
        )

    def test_masters_are_owned_and_invisible_to_the_other_tenant(self):
        with self._as(self.user_a):
            customer = frappe.get_doc({"doctype": "Customer", "customer_name": f"Alpha {self.token}",
                                       "customer_type": "Company"}).insert()
        self.assertEqual(customer.get(MASTER_COMPANY_FIELD), self.company_a)
        with self._as(self.user_b):
            self.assertNotIn(customer.name, frappe.get_list("Customer", pluck="name"))
            self.assertFalse(frappe.has_permission("Customer", "read", customer.name))
        with self._as(self.user_a):
            self.assertIn(customer.name, frappe.get_list("Customer", pluck="name"))

    def test_company_list_shows_only_the_tenant(self):
        with self._as(self.user_a):
            companies = frappe.get_list("Company", pluck="name")
        self.assertIn(self.company_a, companies)
        self.assertNotIn(self.company_b, companies)

    def test_documents_cannot_reference_another_tenants_records(self):
        with self._as(self.user_a):
            item = frappe.get_doc({"doctype": "Item", "item_code": f"ALPHA-{self.token}", "item_name": "Alpha",
                                   "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name")
                                   or "All Item Groups",
                                   "stock_uom": "Nos", "is_stock_item": 0}).insert()
        with self._as(self.user_b):
            order = frappe.get_doc({"doctype": "Sales Order", "company": self.company_b,
                                    "items": [{"item_code": item.name, "qty": 1}]})
            with self.assertRaises(frappe.PermissionError):
                tenant.validate_company_document(order)
            foreign = frappe.get_doc({"doctype": "Sales Order", "company": self.company_a})
            with self.assertRaises(frappe.PermissionError):
                tenant.bind_company_document(foreign)

    def test_desk_guard_and_report_company_pin(self):
        with self._as(self.user_a):
            frappe.local.request = SimpleNamespace(path="/app/hr-settings")
            frappe.local.form_dict = frappe._dict()
            desk_guard.restrict_accounts_desk_request()
            self.assertEqual(frappe.flags.accounts_saas_redirect, "/desk/accounts-home")

            frappe.local.request = SimpleNamespace(path="/api/method/frappe.desk.query_report.run")
            frappe.local.form_dict = frappe._dict(report_name="General Ledger",
                                                  filters=json.dumps({"company": self.company_a}))
            desk_guard.restrict_accounts_desk_request()
            self.assertEqual(json.loads(frappe.local.form_dict.filters)["company"], self.company_a)

            frappe.local.form_dict = frappe._dict(company=self.company_b)
            frappe.local.request = SimpleNamespace(path="/api/method/erpnext.accounts.utils.get_balance_on")
            with self.assertRaises(frappe.PermissionError):
                desk_guard.restrict_accounts_desk_request()
        frappe.local.request = None
        frappe.flags.accounts_saas_redirect = None

    def test_seed_is_idempotent_and_owned(self):
        first = seed.run_accounts_seed(self.company_a, "test")
        second = seed.run_accounts_seed(self.company_a, "test")
        self.assertEqual(first["walk_in_customer"], second["walk_in_customer"])
        self.assertEqual(second["created"], [])
        self.assertEqual(frappe.db.get_value("Customer", first["walk_in_customer"], MASTER_COMPANY_FIELD), self.company_a)
        self.assertEqual(frappe.db.get_value("Warehouse", first["warehouse"], "company"), self.company_a)

    def test_team_admin_adds_colleague_but_never_another_tenant(self):
        colleague = f"ras-clerk-{self.token}@example.com"
        self.cleanup.append(("User", colleague))
        with self._as(self.user_a):
            team_access.add_member(colleague, "Clerk", "Sales User")
            with self.assertRaises(frappe.ValidationError):
                team_access.add_member(self.user_b, "Intruder", "Accountant")
        self.assertIn("Reckon Accounts SaaS Sales User", frappe.get_roles(colleague))
        with self._as(self.user_a):
            self.assertIn(colleague, frappe.get_list("User", pluck="name"))
            self.assertNotIn(self.user_b, frappe.get_list("User", pluck="name"))
