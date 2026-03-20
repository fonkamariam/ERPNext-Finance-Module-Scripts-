frappe.query_reports["Besu"] = {
    filters: [

        // Company filter
        {
            fieldname: "company",
            label: "Company",
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1
        },
         // Periodicity / Quick Select
        {
            fieldname: "periodicity",
            label: "Periodicity",
            fieldtype: "Select",
            options: ["", "Monthly", "Quarterly", "Half-Yearly", "Yearly"],
            default: "Yearly",
            on_change: function(report) {
                report.refresh();
            }
        }

    ], formatter: function(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    // Apply ONLY to Account column
    if (column.fieldname === "account" && data.account_name) {

        // Skip section headers like Income / Expenses
        if (data.account && data.account.includes("<b>")) return value;
        
        // Get filter values safely (they might be undefined/empty)
        let company = frappe.query_report.get_filter_value("company") || "";
        let from_date = frappe.query_report.get_filter_value("from_date");
        let to_date   = frappe.query_report.get_filter_value("to_date");

        // Set smart defaults if missing
        if (!from_date || from_date === "") {
            // Start of current calendar year (simple & common)
            from_date = new Date().getFullYear() + "-01-01";

        }

        if (!to_date || to_date === "") {
            // Default to today
            to_date = frappe.datetime.get_today();
        }

        // Build the route safely
        return `<a href="#" onclick="
            frappe.set_route('query-report', 'General Ledger', {
                company: '${company.replace(/'/g, "\\'")}',  // escape single quotes if any
                account: '${data.account_name.replace(/'/g, "\\'")}',
                from_date: '${from_date}',
                to_date: '${to_date}'
            });
            return false;  // prevent default link behavior
        ">${value}</a>`;
    }

    return value;
}
}

        
