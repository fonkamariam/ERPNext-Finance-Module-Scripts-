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

    ]
}

        
