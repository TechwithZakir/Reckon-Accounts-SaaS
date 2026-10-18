# Reckon Accounts SaaS

Single-company SaaS accounting for small businesses on Frappe/ERPNext v15 and v16:
**sales, purchase, stock and accounting** with Tally-style books. App name:
`reckon_accounts_saas`.

It is a module plugin for [Reckon SaaS Platform](https://github.com/TechwithZakir/Reckon-SaaS-Platform),
built the same way as [Reckon Distribution SaaS](https://github.com/TechwithZakir/Reckon-Distribution-SaaS).
ERPNext remains the accounting and stock engine, and
[Reckon Accounts](https://github.com/TechwithZakir/Reckon-Accounts) provides the voucher entry,
dashboard and 25 Tally-style reports. This app adds what a SaaS tenant needs:

- **One company per tenant.** Every tenant user works in exactly one Company. All
  sales, purchase, stock and accounting records, and masters such as customers
  and items, are isolated per company.
- **Signup to ready in one flow.** Plans for the `accounts` module are sold on
  `/reckonerp-signup?module=accounts`. After email/SMS verification and payment,
  the platform creates the company. This app then seeds it with a walk-in
  customer, a cash supplier, company price lists, a store and a fiscal year.
- **A home page for non-accountants.** The page shows today's sales, receivables
  and payables, cash and bank, stock value, quick actions ("Sales Invoice",
  "Receive Payment", "Purchase Bill", ...), recent documents, items to reorder,
  and a getting-started checklist.
- **Lean forms.** Tenant users see only the fields a small business needs. A
  **Show all fields** button reveals everything on demand.
- **Team & Access.** The company admin invites colleagues by email as Company
  Admin, Company Manager, Accountant, Sales User, Purchase User or Stock User.
- **Bangla and English.** The page text is translatable (`translations/bn.csv`).

## Install

```bash
bench get-app https://github.com/TechwithZakir/Reckon-SaaS-Platform   # skip if already installed
R="python apps/reckon_saas_platform/scripts/reckon_bench.py"
$R get-app https://github.com/TechwithZakir/Reckon-Accounts
$R get-app https://github.com/TechwithZakir/Reckon-Accounts-SaaS
bench --site <site> install-app reckon_accounts reckon_accounts_saas
bench --site <site> migrate
```

`reckon_bench.py get-app` updates an app that is already installed instead of
re-cloning it, and repairs `sites/apps.txt` if a failed clone leaves a repo name
such as `Reckon-Accounts` in it. Update later with
`$R update reckon_accounts reckon_accounts_saas`. See the
[platform README](https://github.com/TechwithZakir/Reckon-SaaS-Platform#installing-and-updating-apps-safely).

After installing:

1. In **SaaS Platform → Modules**, check that the **Accounts** module exists and is
   *Available for Sale*.
2. Create one or more **SaaS Plans** with *Module = accounts*.
3. Share `https://<site>/reckonerp-signup?module=accounts` with prospects.

Reckon Distribution can run on the same site. A company that subscribes to both
modules gets both workspaces: each module's Desk guard allows the union of the
modules the company subscribes to.

## How tenant isolation works

| Record | Rule |
|---|---|
| Documents with a `company` field: quotations, orders, delivery notes, invoices, payments, journal entries, stock entries, ledgers, warehouses, accounts, tax templates | Listed, opened and saved only for the tenant Company. The company is stamped on save and cannot change. |
| Customer, Supplier, Item, Price List, Item Price, Address, Contact | Owned through the `rd_company` field, the same field Reckon Distribution uses. |
| Item Group, Brand, Customer Group, Supplier Group, Territory, Sales Person | Shared rows (no owner) are read-only for tenants. Rows a tenant creates are private to it. |
| Bin (stock levels) | Scoped through its warehouse's company. |
| User | Tenant users see themselves and their colleagues only. |

In addition:

- **Cross-tenant references are refused on save.** A customer, item, warehouse,
  account or price list belonging to another tenant cannot be used.
- **The Desk guard limits what tenants can open.** Tenant users reach only the
  Accounts pages, the listed doctypes and the listed reports; other Desk routes
  redirect to the home page.
- **API calls are checked.** A call that passes another tenant's `company`,
  `warehouse`, `item_code`, `customer`, `supplier`, `party`, `account` or
  `price_list` is refused, including inside an `args` JSON object.
- **Report company is pinned.** Query reports run raw SQL, so their `company`
  filter is forced to the tenant's company.
- **Vendors are not restricted.** Vendor administrators (Reckon Vendor Superuser)
  and Administrator see everything. A tenant user can never hold System Manager
  or Reckon Vendor Superuser (enforced by the platform).

## Roles

| Profile | Can do |
|---|---|
| Company Admin | Everything, including Team & Access |
| Company Manager | Everything except Team & Access |
| Accountant | Accounting, payments, Tally-style books and reports |
| Sales User | Quotations, sales orders, deliveries, sales invoices, customer payments |
| Purchase User | Purchase orders, receipts, bills, supplier payments |
| Stock User | Items, warehouses, stock entries and stock counts |

Profiles map to ERPNext roles plus a `Reckon Accounts SaaS *` role. The role
sync runs when a Tenant User Assignment is saved and on every migrate, never per
request.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

These database-free tests run in CI.

```bash
scripts/test_release_gate.sh --site <test-site>
```

These bench integration tests need a dedicated test site with this app installed.

## Known limits

- ERPNext has many whitelisted form helpers. The guard checks their parameters
  for another tenant's records, but it does not maintain a full allowlist of
  every `erpnext.*` method.
- Mode of Payment is a global ERPNext record. Its per-company account rows are
  visible to every tenant that opens it.
- Lean forms hide fields in the browser only. Server-side permissions decide what
  a user may change.
