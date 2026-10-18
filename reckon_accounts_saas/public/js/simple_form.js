// Lean forms for Accounts SaaS tenant users. See reckon_accounts_saas/simple_forms.py.
(function () {
    // Frappe loads this file once per doctype form; register the handlers only once.
    if (window.__reckonAccountsSimpleForms) return;
    window.__reckonAccountsSimpleForms = true;
    const LAYOUT = new Set(["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"]);
    const STORE_KEY = "reckon_accounts_saas_show_all";

    function config() {
        return (frappe.boot && frappe.boot.reckon_simple_forms) || {};
    }

    function showAll(doctype) {
        try {
            return JSON.parse(localStorage.getItem(STORE_KEY) || "{}")[doctype] === true;
        } catch (e) {
            return false;
        }
    }

    function setShowAll(doctype, value) {
        try {
            const stored = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
            stored[doctype] = value;
            localStorage.setItem(STORE_KEY, JSON.stringify(stored));
        } catch (e) {
            /* private mode: the toggle still works for this page */
        }
    }

    function hasValue(frm, df) {
        const value = frm.doc[df.fieldname];
        if (Array.isArray(value)) return value.length > 0;
        if (df.fieldtype === "Check") return false;
        return value !== undefined && value !== null && value !== "" && value !== 0 && value !== df.default;
    }

    function apply(frm) {
        const cfg = config();
        const essentials = (cfg.fields || {})[frm.doctype];
        if (!cfg.enabled || !essentials) return;
        const keep = new Set(essentials);
        const lean = !showAll(frm.doctype);
        (frm.meta.fields || []).forEach(function (df) {
            if (LAYOUT.has(df.fieldtype)) return;
            if ((cfg.always_hidden || []).includes(df.fieldname)) {
                frm.toggle_display(df.fieldname, false);
                return;
            }
            const required = df.reqd || (frm.fields_dict[df.fieldname] && frm.fields_dict[df.fieldname].df.reqd);
            // Never hide a required field, or one already holding data the user should see.
            const visible = !lean || keep.has(df.fieldname) || required || (!frm.is_new() && hasValue(frm, df) && df.fieldtype !== "Read Only" && !df.hidden && !df.read_only);
            if (!df.hidden) frm.toggle_display(df.fieldname, visible);
        });
        frm.remove_custom_button(__("Show all fields"));
        frm.remove_custom_button(__("Show fewer fields"));
        frm.add_custom_button(lean ? __("Show all fields") : __("Show fewer fields"), function () {
            setShowAll(frm.doctype, lean);
            frm.refresh();
        });
    }

    const doctypes = Object.keys((frappe.boot && frappe.boot.reckon_simple_forms || {}).fields || {
        "Customer": 1, "Supplier": 1, "Item": 1, "Quotation": 1, "Sales Order": 1, "Delivery Note": 1,
        "Sales Invoice": 1, "Purchase Order": 1, "Purchase Receipt": 1, "Purchase Invoice": 1,
        "Payment Entry": 1, "Journal Entry": 1, "Stock Entry": 1, "Stock Reconciliation": 1,
        "Material Request": 1, "Warehouse": 1,
    });
    doctypes.forEach(function (doctype) {
        frappe.ui.form.on(doctype, {
            refresh: apply,
            onload_post_render: apply,
        });
    });
})();
