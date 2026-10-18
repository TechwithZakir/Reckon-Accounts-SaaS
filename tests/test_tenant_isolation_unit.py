"""Tenant isolation rules for documents and masters (no database)."""

from __future__ import annotations

import unittest

from frappe_stub import FakeDoc, app_modules


class QueryConditionTests(unittest.TestCase):
    def test_company_documents_are_scoped_to_the_tenant(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            self.assertEqual(
                tenant.get_company_document_query("u", "Sales Invoice"),
                "`tabSales Invoice`.`company` = 'Acme'",
            )

    def test_vendor_bypass_sees_everything(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.tenant_security.user_can_bypass_tenant.return_value = True
            for build in (tenant.get_company_document_query, tenant.get_owned_master_query, tenant.get_bin_query):
                self.assertEqual(build("vendor", "Sales Invoice"), "")

    def test_owned_masters_are_strict(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            self.assertEqual(tenant.get_owned_master_query("u", "Customer"), "`tabCustomer`.`rd_company` = 'Acme'")

    def test_shared_taxonomies_include_unowned_rows(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            condition = tenant.get_owned_master_query("u", "Item Group")
        self.assertIn("is null", condition)
        self.assertIn("= 'Acme'", condition)

    def test_missing_owner_column_hides_everything(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.db.has_column.return_value = False
            self.assertEqual(tenant.get_owned_master_query("u", "Customer"), "1=0")

    def test_company_names_are_escaped(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.tenant_security.require_tenant.return_value.company = "O'Neil"
            self.assertIn("'O''Neil'", tenant.get_company_document_query("u", "Sales Invoice"))

    def test_bin_user_and_company_queries(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            self.assertIn("company = 'Acme'", tenant.get_bin_query("u", "Bin"))
            self.assertIn("`tabTenant User Assignment`", tenant.get_user_query("u", "User"))
            self.assertEqual(tenant.get_company_query("u", "Company"), "`tabCompany`.`name` = 'Acme'")


class DocumentPermissionTests(unittest.TestCase):
    def test_own_and_foreign_documents(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.db.get_value.return_value = "Acme"
            self.assertTrue(tenant.has_company_document_permission(FakeDoc("Sales Invoice", "SI-1", company="Acme"), ptype="read"))
            ctx.frappe.db.get_value.return_value = "Rival"
            self.assertFalse(tenant.has_company_document_permission(FakeDoc("Sales Invoice", "SI-2", company="Acme"), ptype="read"))

    def test_new_documents_cannot_target_another_company(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            self.assertTrue(tenant.has_company_document_permission(FakeDoc("Sales Invoice", new=True), ptype="create"))
            self.assertFalse(
                tenant.has_company_document_permission(FakeDoc("Sales Invoice", new=True, company="Rival"), ptype="create")
            )

    def test_shared_taxonomy_is_read_only(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.db.get_value.return_value = None
            group = FakeDoc("Item Group", "All Item Groups")
            self.assertTrue(tenant.has_owned_master_permission(group, ptype="read"))
            self.assertFalse(tenant.has_owned_master_permission(group, ptype="write"))

    def test_foreign_master_is_hidden(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.db.get_value.return_value = "Rival"
            self.assertFalse(tenant.has_owned_master_permission(FakeDoc("Customer", "C-1", rd_company="Rival"), ptype="read"))
            ctx.frappe.db.get_value.return_value = "Acme"
            self.assertTrue(tenant.has_owned_master_permission(FakeDoc("Customer", "C-2", rd_company="Acme"), ptype="read"))

    def test_company_record_cannot_be_created_or_deleted_by_tenant(self):
        with app_modules("tenant") as (_ctx, (tenant,)):
            self.assertTrue(tenant.has_company_permission(FakeDoc("Company", "Acme"), ptype="write"))
            self.assertFalse(tenant.has_company_permission(FakeDoc("Company", "Acme"), ptype="delete"))
            self.assertFalse(tenant.has_company_permission(FakeDoc("Company", "Rival"), ptype="read"))

    def test_user_without_tenant_sees_nothing(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.tenant_security.require_tenant.side_effect = ctx.tenant_security.TenantResolutionError("none")
            self.assertFalse(tenant.has_company_document_permission(FakeDoc("Sales Invoice", "SI-1", company="Acme"), ptype="read"))

    def test_colleagues_are_visible_other_tenants_are_not(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.session.user = "owner@acme.example"
            ctx.frappe.db.exists.return_value = None
            self.assertTrue(tenant.has_user_permission(FakeDoc("User", "owner@acme.example"), ptype="write"))
            self.assertFalse(tenant.has_user_permission(FakeDoc("User", "boss@rival.example"), ptype="read"))
            ctx.frappe.db.exists.return_value = "TUA-1"
            self.assertTrue(tenant.has_user_permission(FakeDoc("User", "clerk@acme.example"), ptype="read"))
            self.assertFalse(tenant.has_user_permission(FakeDoc("User", "clerk@acme.example"), ptype="write"))


class SaveTimeTests(unittest.TestCase):
    def test_company_is_stamped_and_immutable(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            doc = FakeDoc("Sales Invoice", new=True, fields=("company",))
            tenant.bind_company_document(doc)
            self.assertEqual(doc.company, "Acme")
            with self.assertRaises(ctx.frappe.PermissionError):
                tenant.bind_company_document(FakeDoc("Sales Invoice", new=True, company="Rival"))
            ctx.frappe.db.get_value.return_value = "Rival"
            with self.assertRaises(ctx.frappe.PermissionError):
                tenant.bind_company_document(FakeDoc("Sales Invoice", "SI-9", company="Acme"))

    def _validate(self, owners, **doc_values):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.frappe.db.get_value.side_effect = lambda doctype, name, field: owners.get((doctype, name))
            ctx.frappe.db.exists.return_value = True
            tenant.validate_company_document(FakeDoc("Sales Invoice", "SI-1", **doc_values))

    def test_foreign_customer_item_warehouse_and_account_are_refused(self):
        own = {("Customer", "C-A"): "Acme", ("Item", "I-A"): "Acme", ("Warehouse", "Stores - A"): "Acme"}
        self._validate(own, customer="C-A", tables={"items": [{"item_code": "I-A", "warehouse": "Stores - A"}]})
        cases = [
            {"customer": "C-R"},
            {"tables": {"items": [{"item_code": "I-R"}]}},
            {"tables": {"items": [{"item_code": "I-A", "warehouse": "Stores - R"}]}},
            {"set_warehouse": "Stores - R"},
            {"tables": {"accounts": [{"account": "Cash - R"}]}},
            {"party_type": "Supplier", "party": "S-R"},
        ]
        foreign = {**own, ("Customer", "C-R"): "Rival", ("Item", "I-R"): "Rival", ("Warehouse", "Stores - R"): "Rival",
                   ("Account", "Cash - R"): "Rival", ("Supplier", "S-R"): "Rival"}
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(Exception) as raised:
                    self._validate(foreign, **case)
                self.assertEqual(type(raised.exception).__name__, "PermissionError")

    def test_global_price_list_is_accepted_but_foreign_is_not(self):
        self._validate({}, selling_price_list="Standard Selling")
        with self.assertRaises(Exception) as raised:  # noqa: B017 - stub PermissionError class differs per context
            self._validate({("Price List", "Rival Selling"): "Rival"}, selling_price_list="Rival Selling")
        self.assertEqual(type(raised.exception).__name__, "PermissionError")

    def test_new_master_is_stamped_and_owner_is_protected(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            item = FakeDoc("Item", new=True, fields=("rd_company",))
            tenant.bind_owned_master(item)
            self.assertEqual(item.rd_company, "Acme")
            ctx.frappe.db.get_value.return_value = "Rival"
            with self.assertRaises(ctx.frappe.PermissionError):
                tenant.bind_owned_master(FakeDoc("Item", "I-R", fields=("rd_company",), rd_company="Acme"))

    def test_vendor_saves_are_not_rebound(self):
        with app_modules("tenant") as (ctx, (tenant,)):
            ctx.tenant_security.user_can_bypass_tenant.return_value = True
            doc = FakeDoc("Sales Invoice", new=True, company="Rival")
            tenant.bind_company_document(doc)
            tenant.validate_company_document(doc)
            self.assertEqual(doc.company, "Rival")


if __name__ == "__main__":
    unittest.main()
