frappe.pages["accounts-home"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Home"), single_column: true });
    page.set_primary_action(__("New Sales Invoice"), () => frappe.new_doc("Sales Invoice"), "add");
    page.add_inner_button(__("Refresh"), () => load());

    const $body = $('<div class="ras-home"></div>').appendTo(page.main);
    const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
    let currency = "BDT";
    const money = (value) => format_currency(value || 0, currency, 0);

    const ACTIONS = [
        { label: __("Sales Invoice"), hint: __("Bill a customer"), icon: "receipt-text", run: () => frappe.new_doc("Sales Invoice") },
        { label: __("Purchase Bill"), hint: __("Record a supplier bill"), icon: "file-text", run: () => frappe.new_doc("Purchase Invoice") },
        { label: __("Receive Payment"), hint: __("Money from a customer"), icon: "arrow-down-to-line",
          run: () => frappe.new_doc("Payment Entry", { payment_type: "Receive", party_type: "Customer" }) },
        { label: __("Make Payment"), hint: __("Pay a supplier"), icon: "arrow-up-from-line",
          run: () => frappe.new_doc("Payment Entry", { payment_type: "Pay", party_type: "Supplier" }) },
        { label: __("Expense / Income"), hint: __("Quick voucher entry"), icon: "keyboard", run: () => frappe.set_route("voucher-entry") },
        { label: __("Office Expense"), hint: __("Record a paid office expense"), icon: "wallet", run: () => frappe.new_doc("Office Expense") },
        { label: __("Quotation"), hint: __("Send a price offer"), icon: "file-pen", run: () => frappe.new_doc("Quotation") },
        { label: __("New Item"), hint: __("Product or service"), icon: "package", run: () => frappe.new_doc("Item") },
        { label: __("Stock Transfer"), hint: __("Move or adjust stock"), icon: "arrow-left-right", run: () => frappe.new_doc("Stock Entry") },
    ];
    const REPORTS = [
        ["Day Book", __("Day Book")], ["Cash Book", __("Cash Book")], ["Party Ledger", __("Party Ledger")],
        ["Accounts Receivable", __("Who owes you")], ["Accounts Payable", __("Who you owe")],
        ["Sales Register", __("Sales Register")], ["Purchase Register", __("Purchase Register")],
        ["Gross Profit", __("Gross Profit")], ["Stock Balance", __("Stock Balance")],
        ["Profit and Loss Statement", __("Profit and Loss")], ["Balance Sheet", __("Balance Sheet")],
        ["Trial Balance", __("Trial Balance")],
    ];

    function kpi(label, value, route, tone) {
        return `<a class="ras-kpi ${tone || ""}" href="${route}"><span>${esc(label)}</span><strong>${esc(money(value))}</strong></a>`;
    }

    function table(title, rows, columns, doctype, empty) {
        const body = rows.length
            ? rows.map((row) => `<tr>${columns.map((col) => `<td>${col(row)}</td>`).join("")}</tr>`).join("")
            : `<tr><td class="ras-muted" colspan="${columns.length}">${esc(empty)}</td></tr>`;
        return `<section class="ras-card"><header><h4>${esc(title)}</h4>
            <a href="/app/${frappe.router.slug(doctype)}">${esc(__("View all"))}</a></header>
            <table class="ras-table"><tbody>${body}</tbody></table></section>`;
    }

    function docLink(doctype, name) {
        return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(name)}</a>`;
    }

    function render(data) {
        currency = data.currency || "BDT";
        const k = data.kpis || {};
        const pending = (data.checklist || []).filter((step) => !step.done);
        $body.html(`
            <div class="ras-hello">
                <div><h3>${esc(data.company)}</h3><p>${esc(frappe.datetime.str_to_user(frappe.datetime.get_today()))}</p></div>
            </div>
            <div class="ras-kpis">
                ${kpi(__("Sales today"), k.sales_today, "/app/sales-invoice?docstatus=1")}
                ${kpi(__("Sales this month"), k.sales_month, "/app/query-report/Sales Register", "is-green")}
                ${kpi(__("Purchases this month"), k.purchase_month, "/app/query-report/Purchase Register")}
                ${kpi(__("Customers owe you"), k.receivable, "/app/query-report/Accounts Receivable", "is-blue")}
                ${kpi(__("You owe suppliers"), k.payable, "/app/query-report/Accounts Payable", "is-amber")}
                ${kpi(__("Cash and bank"), k.cash_bank, "/app/query-report/Cash Book", "is-green")}
                ${kpi(__("Stock value"), k.stock_value, "/app/query-report/Stock Balance")}
            </div>
            ${pending.length ? `<section class="ras-card ras-checklist"><header><h4>${esc(__("Get started"))}</h4>
                <span class="ras-muted">${esc(__("{0} of {1} done", [data.checklist.length - pending.length, data.checklist.length]))}</span></header>
                <div class="ras-steps">${data.checklist.map((step) => `<button class="ras-step ${step.done ? "is-done" : ""}" data-target="${esc(step.target)}">
                    <span class="ras-tick">${step.done ? "✓" : ""}</span>${esc(step.label)}</button>`).join("")}</div></section>` : ""}
            <section class="ras-actions">${ACTIONS.map((a, i) => `<button class="ras-action" data-action="${i}">
                <span class="ras-action-icon">${frappe.utils.icon(a.icon, "md")}</span>
                <span><strong>${esc(a.label)}</strong><small>${esc(a.hint)}</small></span></button>`).join("")}</section>
            <div class="ras-grid">
                ${table(__("Recent sales"), data.recent_sales || [], [
                    (r) => docLink("Sales Invoice", r.name), (r) => esc(r.party), (r) => esc(money(r.grand_total)),
                    (r) => `<span class="indicator-pill ${r.outstanding_amount > 0 ? "orange" : "green"}">${esc(__(r.status))}</span>`,
                ], "Sales Invoice", __("No sales yet. Create your first invoice."))}
                ${table(__("Recent purchases"), data.recent_purchases || [], [
                    (r) => docLink("Purchase Invoice", r.name), (r) => esc(r.party), (r) => esc(money(r.grand_total)),
                    (r) => `<span class="indicator-pill ${r.outstanding_amount > 0 ? "orange" : "green"}">${esc(__(r.status))}</span>`,
                ], "Purchase Invoice", __("No purchase bills yet."))}
                ${table(__("Items to reorder"), data.low_stock || [], [
                    (r) => docLink("Item", r.item_code), (r) => esc(r.warehouse), (r) => esc(r.projected_qty),
                ], "Item", __("Stock levels look fine."))}
                <section class="ras-card"><header><h4>${esc(__("Reports"))}</h4></header>
                    <div class="ras-reports">${REPORTS.map(([name, label]) =>
                        `<a href="/app/query-report/${encodeURIComponent(name)}">${esc(label)}</a>`).join("")}</div></section>
            </div>`);
    }

    $body.on("click", "[data-action]", function () {
        ACTIONS[Number($(this).attr("data-action"))].run();
    });
    $body.on("click", "[data-target]", function () {
        const target = $(this).attr("data-target");
        if (target === "accounts-team") frappe.set_route("accounts-team");
        else frappe.new_doc(target);
    });

    function load() {
        frappe.call("reckon_accounts_saas.home.get_home_data").then((r) => render(r.message || {}));
    }

    $("<style>").text(`
        .ras-home { padding: 4px 0 32px; }
        .ras-hello h3 { margin: 0; font-size: 20px; }
        .ras-hello p { margin: 2px 0 16px; color: var(--text-muted); }
        .ras-kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-bottom: 18px; }
        .ras-kpi { display: block; padding: 14px 16px; border-radius: var(--border-radius-lg); background: var(--card-bg);
            border: 1px solid var(--border-color); color: var(--text-color); text-decoration: none; }
        .ras-kpi:hover { border-color: var(--primary); text-decoration: none; }
        .ras-kpi span { display: block; font-size: var(--text-sm); color: var(--text-muted); }
        .ras-kpi strong { display: block; font-size: 22px; margin-top: 4px; }
        .ras-kpi.is-green strong { color: var(--green-600, #2a9a00); }
        .ras-kpi.is-blue strong { color: var(--blue-600, #0b78ab); }
        .ras-kpi.is-amber strong { color: var(--orange-600, #b45309); }
        .ras-actions { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 18px; }
        .ras-action { display: flex; gap: 12px; align-items: center; text-align: left; padding: 12px 14px; border-radius: var(--border-radius-lg);
            border: 1px solid var(--border-color); background: var(--card-bg); cursor: pointer; }
        .ras-action:hover { border-color: var(--primary); }
        .ras-action-icon { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: var(--bg-light-gray, #f3f6fa); }
        .ras-action strong { display: block; font-size: 14px; color: var(--text-color); }
        .ras-action small { display: block; color: var(--text-muted); }
        .ras-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
        .ras-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); padding: 14px 16px; margin-bottom: 14px; }
        .ras-card header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .ras-card h4 { margin: 0; font-size: 15px; }
        .ras-table { width: 100%; font-size: 13px; }
        .ras-table td { padding: 7px 4px; border-top: 1px solid var(--border-color); }
        .ras-muted { color: var(--text-muted); }
        .ras-reports { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px 12px; font-size: 13px; }
        .ras-steps { display: flex; flex-wrap: wrap; gap: 8px; }
        .ras-step { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 999px; border: 1px dashed var(--border-color);
            background: var(--card-bg); cursor: pointer; font-size: 13px; }
        .ras-step.is-done { border-style: solid; color: var(--text-muted); text-decoration: line-through; }
        .ras-tick { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-color); display: grid; place-items: center; font-size: 11px; }
        .ras-step.is-done .ras-tick { background: var(--green-500, #3cd400); border-color: var(--green-500, #3cd400); color: #fff; }
    `).appendTo($body.parent());

    load();
};
