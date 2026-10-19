"""The v16 left rail is shipped as a file, so ``bench migrate`` stops deleting it as an orphan.

Frappe v16's ``remove_orphan_entities`` deletes every standard Workspace Sidebar whose ``app`` has
no ``<app>/workspace_sidebar/<frappe.scrub(name)>.json``. These tests pin that path and keep the
after_migrate code reading the same file.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from frappe_stub import REPO_ROOT, app_modules


def scrub(text: str) -> str:
    return text.replace(" ", "_").replace("-", "_").lower()


def shipped_sidebar(app: str, name: str):
    """Mirror ``frappe.model.sync.check_if_record_exists("app", ...)`` for a Workspace Sidebar."""
    return REPO_ROOT / app / "workspace_sidebar" / f"{scrub(name)}.json"


class ShippedSidebarFileTests(unittest.TestCase):
    def test_file_sits_where_the_orphan_sweep_looks(self):
        with app_modules("install", "constants") as (_ctx, (install, c)):
            definition = json.loads(install.SIDEBAR_FILE.read_text(encoding="utf-8"))
            path = shipped_sidebar(definition["app"], c.WORKSPACE_SIDEBAR)
            self.assertEqual(install.SIDEBAR_FILE.resolve(), path.resolve())
        self.assertTrue(path.exists())
        self.assertEqual(definition["doctype"], "Workspace Sidebar")
        self.assertEqual(definition["name"], c.WORKSPACE_SIDEBAR)
        self.assertEqual(definition["app"], "reckon_accounts_saas")
        self.assertEqual(definition["standard"], 1)
        modules = (REPO_ROOT / "reckon_accounts_saas/modules.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn(definition["module"], modules)

    def test_file_has_a_fixed_timestamp_so_migrate_does_not_reimport_it(self):
        # Without `modified`, Frappe's import treats the file as newer than the database row on
        # every migrate and deletes and re-inserts it.
        with app_modules("install") as (_ctx, (install,)):
            definition = json.loads(install.SIDEBAR_FILE.read_text(encoding="utf-8"))
        self.assertRegex(definition["modified"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")

    def test_links_use_the_app_constants(self):
        with app_modules("install", "constants") as (ctx, (install, c)):
            ctx.frappe.db.exists.return_value = True
            items = install.workspace_sidebar_doc()["items"]
        self.assertEqual(items[0]["link_to"], c.HOME_PAGE)
        self.assertIn(c.TEAM_PAGE, {item.get("link_to") for item in items})


class AfterMigrateUsesTheFileTests(unittest.TestCase):
    def test_definition_is_the_file_minus_missing_links(self):
        with app_modules("install") as (ctx, (install,)):
            shipped = json.loads(install.SIDEBAR_FILE.read_text(encoding="utf-8"))
            ctx.frappe.db.exists.side_effect = lambda doctype, name: name != "Gross Profit"
            definition = install.workspace_sidebar_doc()
        expected = [item for item in shipped["items"] if item.get("link_to") != "Gross Profit"]
        self.assertEqual(definition["items"], expected)
        self.assertEqual(len(definition["items"]), len(shipped["items"]) - 1)
        self.assertNotIn("modified", definition)
        self.assertEqual(
            {k: v for k, v in definition.items() if k != "items"},
            {k: v for k, v in shipped.items() if k not in {"items", "modified"}},
        )

    def test_missing_sidebar_is_inserted_from_the_file(self):
        with app_modules("install", "constants") as (ctx, (install, c)):
            ctx.frappe.db.exists.side_effect = lambda doctype, name=None: doctype != "Workspace Sidebar"
            install.ensure_workspace_sidebar()
            inserted = ctx.frappe.get_doc.call_args.args[0]
        self.assertEqual(inserted["name"], c.WORKSPACE_SIDEBAR)
        self.assertEqual(inserted["app"], "reckon_accounts_saas")
        ctx.frappe.get_doc.return_value.insert.assert_called_once()

    def test_existing_sidebar_gets_the_file_rows(self):
        with app_modules("install") as (ctx, (install,)):
            ctx.frappe.db.exists.return_value = True
            sidebar = Mock()
            ctx.frappe.get_doc.return_value = sidebar
            install.ensure_workspace_sidebar()
            shipped = json.loads(install.SIDEBAR_FILE.read_text(encoding="utf-8"))
        sidebar.set.assert_called_once_with("items", shipped["items"])
        self.assertEqual(sidebar.header_icon, shipped["header_icon"])
        sidebar.save.assert_called_once()

    def test_v15_without_workspace_sidebar_is_left_alone(self):
        with app_modules("install") as (ctx, (install,)):
            ctx.frappe.db.exists.return_value = None
            install.ensure_workspace_sidebar()
        ctx.frappe.get_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
