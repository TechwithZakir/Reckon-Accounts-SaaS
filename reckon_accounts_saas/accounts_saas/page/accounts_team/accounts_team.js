frappe.pages["accounts-team"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Team & Access"), single_column: true });
    const $body = $('<div class="ras-team"></div>').appendTo(page.main);
    const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
    const ROLE_HELP = {
        "Company Admin": __("Everything, including team and settings"),
        "Company Manager": __("Everything except team access"),
        "Accountant": __("Accounting, payments and reports"),
        "Sales User": __("Quotations, sales invoices and customer payments"),
        "Purchase User": __("Purchase orders, bills and supplier payments"),
        "Stock User": __("Items, warehouses and stock movements"),
    };
    let profiles = [];

    page.set_primary_action(__("Add Team Member"), () => addMember(), "add");

    function addMember() {
        const dialog = new frappe.ui.Dialog({
            title: __("Add Team Member"),
            fields: [
                { fieldname: "full_name", label: __("Full Name"), fieldtype: "Data", reqd: 1 },
                { fieldname: "email", label: __("Email"), fieldtype: "Data", options: "Email", reqd: 1 },
                { fieldname: "role_profile", label: __("Role"), fieldtype: "Select", reqd: 1,
                  options: profiles.join("\n"), default: "Sales User",
                  description: __("They receive an email with a link to set their password.") },
            ],
            primary_action_label: __("Add"),
            primary_action(values) {
                frappe.call({ method: "reckon_accounts_saas.team_access.add_member", args: values, freeze: true })
                    .then(() => { dialog.hide(); frappe.show_alert({ message: __("Team member added"), indicator: "green" }); load(); });
            },
        });
        dialog.show();
    }

    function update(assignment, values, message) {
        frappe.call({ method: "reckon_accounts_saas.team_access.update_member", args: { assignment, ...values }, freeze: true })
            .then(() => { frappe.show_alert({ message, indicator: "green" }); load(); });
    }

    function render(data) {
        profiles = data.profiles || [];
        const rows = (data.members || []).map((m) => `
            <tr class="${m.active ? "" : "ras-inactive"}">
                <td><strong>${esc(m.full_name)}</strong><div class="text-muted small">${esc(m.user)}</div></td>
                <td>${m.is_self ? esc(__(m.role_profile))
                    : `<select class="form-control input-sm" data-role="${esc(m.assignment)}">${profiles.map((p) =>
                        `<option value="${esc(p)}" ${p === m.role_profile ? "selected" : ""}>${esc(__(p))}</option>`).join("")}</select>`}
                    <div class="text-muted small">${esc(ROLE_HELP[m.role_profile] || "")}</div></td>
                <td>${m.active ? `<span class="indicator-pill green">${esc(__("Active"))}</span>` : `<span class="indicator-pill gray">${esc(__("Inactive"))}</span>`}</td>
                <td>${m.is_self ? `<span class="text-muted small">${esc(__("You"))}</span>`
                    : `<button class="btn btn-xs btn-default" data-toggle-active="${esc(m.assignment)}" data-active="${m.active ? 1 : 0}">
                        ${esc(m.active ? __("Deactivate") : __("Reactivate"))}</button>`}</td>
            </tr>`).join("");
        $body.html(`
            <p class="text-muted">${esc(__("People you add can sign in and work only in {0}.", [data.company]))}</p>
            <div class="ras-team-table"><table class="table table-bordered">
                <thead><tr><th>${esc(__("Person"))}</th><th>${esc(__("Role"))}</th><th>${esc(__("Status"))}</th><th></th></tr></thead>
                <tbody>${rows}</tbody></table></div>
            <h5>${esc(__("What each role can do"))}</h5>
            <ul class="ras-role-help">${profiles.map((p) => `<li><strong>${esc(__(p))}</strong>: ${esc(ROLE_HELP[p] || "")}</li>`).join("")}</ul>`);
    }

    $body.on("change", "[data-role]", function () {
        update($(this).attr("data-role"), { role_profile: $(this).val() }, __("Role updated"));
    });
    $body.on("click", "[data-toggle-active]", function () {
        const active = Number($(this).attr("data-active")) ? 0 : 1;
        update($(this).attr("data-toggle-active"), { active }, active ? __("Access restored") : __("Access removed"));
    });

    function load() {
        frappe.call("reckon_accounts_saas.team_access.get_team").then((r) => render(r.message || {}));
    }

    $("<style>").text(`
        .ras-team-table { overflow-x: auto; }
        .ras-inactive td { opacity: .6; }
        .ras-role-help { padding-left: 18px; color: var(--text-muted); }
    `).appendTo($body.parent());

    load();
};
