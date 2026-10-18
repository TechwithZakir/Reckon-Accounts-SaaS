"""In-memory stand-ins for ``frappe`` and ``reckon_saas_platform`` (no database)."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Dict(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class FakeCache:
    def __init__(self):
        self.store = {}

    def get_value(self, key):
        return self.store.get(key)

    def set_value(self, key, value, expires_in_sec=None):
        self.store[key] = value

    def delete_value(self, key):
        self.store.pop(key, None)


class FakeDoc(_Dict):
    """A document with meta, ``is_new`` and child tables."""

    def __init__(self, doctype, name=None, new=False, fields=(), tables=None, **values):
        super().__init__(doctype=doctype, name=name, **values)
        tables = tables or {}
        object.__setattr__(self, "_new", new)
        object.__setattr__(
            self,
            "meta",
            SimpleNamespace(
                has_field=lambda field: field in fields or field in values or field in tables,
                get_table_fields=lambda: [SimpleNamespace(fieldname=t) for t in tables],
            ),
        )
        for table, rows in tables.items():
            self[table] = [_Dict(row) for row in rows]

    def is_new(self):
        return self._new

    def set(self, key, value):
        self[key] = value


def build_frappe() -> ModuleType:
    frappe = ModuleType("frappe")

    class ValidationError(Exception):
        http_status_code = 417

    class PermissionError(Exception):  # noqa: A001 - mirrors frappe.PermissionError
        http_status_code = 403

    def throw(msg, exc=ValidationError, *args, **kwargs):
        raise exc(msg)

    frappe.ValidationError = ValidationError
    frappe.PermissionError = PermissionError
    frappe._ = lambda text: text
    frappe._dict = _Dict
    frappe.throw = Mock(side_effect=throw)
    frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
    frappe.scrub = lambda text: text.replace(" ", "_").replace("-", "_").lower()
    frappe.session = _Dict(user="owner@acme.example")
    frappe.flags = _Dict()
    frappe.local = _Dict(form_dict=_Dict(), request=None)
    frappe.cache = FakeCache()
    frappe.get_roles = Mock(return_value=[])
    frappe.get_all = Mock(return_value=[])
    frappe.get_doc = Mock()
    frappe.new_doc = Mock()
    frappe.get_hooks = Mock(return_value=[])
    frappe.get_attr = Mock()
    frappe.delete_doc = Mock()
    frappe.clear_cache = Mock()
    frappe.log_error = Mock()
    frappe.get_traceback = Mock(return_value="tb")
    frappe.has_permission = Mock(return_value=True)
    frappe.get_meta = Mock()
    frappe.defaults = SimpleNamespace(get_user_default=Mock(return_value=None))
    frappe.db = Mock()
    frappe.db.escape = lambda value: "'" + str(value).replace("'", "''") + "'"
    frappe.db.has_column = Mock(return_value=True)
    frappe.db.exists = Mock(return_value=None)
    frappe.db.get_value = Mock(return_value=None)
    frappe.db.count = Mock(return_value=0)

    utils = ModuleType("frappe.utils")
    utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision else float(value or 0)
    utils.cint = lambda value: int(value or 0)
    utils.getdate = Mock(name="getdate")
    utils.nowdate = Mock(return_value="2026-10-18")
    utils.get_first_day = Mock(return_value="2026-10-01")
    utils.validate_email_address = lambda value, throw=False: value if value and "@" in value else ""
    frappe.utils = utils
    return frappe


def build_platform(frappe):
    package = ModuleType("reckon_saas_platform")
    package.__path__ = []

    security = ModuleType("reckon_saas_platform.tenant_security")

    class TenantResolutionError(frappe.PermissionError):
        pass

    security.TenantResolutionError = TenantResolutionError
    security.user_can_bypass_tenant = Mock(return_value=False)
    security.require_tenant = Mock(return_value=SimpleNamespace(company="Acme"))
    security.get_user_companies = Mock(return_value=["Acme"])

    saas = ModuleType("reckon_saas_platform.saas")
    saas.get_company_module_keys = Mock(return_value=["accounts"])

    registry = ModuleType("reckon_saas_platform.module_registry")
    registry.get_saas_modules = Mock(return_value=[])

    gate = ModuleType("reckon_saas_platform.saas_gate")
    gate.is_user_gated = Mock(return_value=False)

    accounts = ModuleType("reckon_accounts")
    accounts.__path__ = []
    office_expense_setup = ModuleType("reckon_accounts.office_expense_setup")
    office_expense_setup.ensure_office_expense_defaults = Mock(return_value=[])

    return {
        "reckon_accounts": accounts,
        "reckon_accounts.office_expense_setup": office_expense_setup,
        "reckon_saas_platform": package,
        "reckon_saas_platform.tenant_security": security,
        "reckon_saas_platform.saas": saas,
        "reckon_saas_platform.module_registry": registry,
        "reckon_saas_platform.saas_gate": gate,
    }


@contextmanager
def app_modules(*names: str):
    """Import ``reckon_accounts_saas`` modules against fresh stubs."""
    frappe = build_frappe()
    platform = build_platform(frappe)
    stubs = {"frappe": frappe, "frappe.utils": frappe.utils, **platform}
    saved_path = list(sys.path)
    sys.path.insert(0, str(REPO_ROOT))
    saved = {k: v for k, v in sys.modules.items() if k.startswith("reckon_accounts_saas")}
    for key in saved:
        del sys.modules[key]
    try:
        with patch.dict(sys.modules, stubs):
            modules = [importlib.import_module(f"reckon_accounts_saas.{name}") for name in names]
            yield SimpleNamespace(frappe=frappe, **{k.split(".")[-1]: v for k, v in platform.items()}), modules
    finally:
        for key in [k for k in sys.modules if k.startswith("reckon_accounts_saas")]:
            del sys.modules[key]
        sys.modules.update(saved)
        sys.path[:] = saved_path
