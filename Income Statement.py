def execute(filters=None):
    company   = filters.get("company")
    from_date = filters.get("from_date") or frappe.utils.add_days(frappe.utils.today(), -365)
    to_date   = filters.get("to_date") or frappe.utils.today()
    periodicity = filters.get("periodicity") or "Yearly"
    show_zero_values = int(filters.get("show_zero_values")) if filters.get("show_zero_values") else 0
    

    if not company:
        frappe.throw("Company is required")
        pass
    if not from_date or not to_date:
        frappe.throw("From Date and To Date are required")
    

    # -----------------------------
    # PERIODS
    # -----------------------------
    def get_periods(from_date, to_date, periodicity):
        periods = []
        month_map = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        current = frappe.utils.getdate(from_date)
        end = frappe.utils.getdate(to_date)

        step = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6}.get(periodicity, 12)

        while current <= end:
            start = current
            next_date = frappe.utils.add_months(start, step)
            end_d = frappe.utils.add_days(next_date, -1)

            if end_d > end:
                end_d = end

            if periodicity == "Monthly":
                label = f"{month_map[start.month - 1]} {start.year}"
            else:
                label = f"{month_map[start.month - 1]}{start.year}-{month_map[end_d.month - 1]}{end_d.year}"

            periods.append({
                "from_date": start,
                "to_date": end_d,
                "label": label
            })

            current = next_date

        return periods

    periods = get_periods(from_date, to_date, periodicity)

    # -----------------------------
    # COLUMNS
    # -----------------------------
    columns = [{"label": "Account", "fieldname": "account", "fieldtype": "Data", "width": 300}]

    for i, p in enumerate(periods):
        columns.append({
            "label": p["label"],
            "fieldname": f"p{i}",
            "fieldtype": "Currency",
            "width": 150
        })

    columns.append({"label": "Total", "fieldname": "total", "fieldtype": "Currency", "width": 150})

    # -----------------------------
    # ACCOUNTS
    # -----------------------------
    income_accounts = frappe.db.get_all("Account",
        filters={"company": company, "root_type": "Income", "is_group": 0},
        fields=["name", "account_name", "account_number"]
    )

    expense_accounts = frappe.db.get_all("Account",
        filters={"company": company, "root_type": "Expense", "is_group": 0},
        fields=["name", "account_name", "account_number"]
    )

    # -----------------------------
    # BUILD ROWS
    # -----------------------------
    def build_rows(accounts, root_type):
        rows = []
        period_totals = [0] * len(periods)
        grand_total = 0

        for acc in accounts:
            row = {
                "account": f"{acc.account_number or ''} {acc.account_name}",
                "account_name": acc.name
            }

            row_total = 0
            has_value = False

            for i, p in enumerate(periods):

                if root_type == "Income":
                    res = frappe.db.sql("""
                        SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                        FROM `tabGL Entry`
                        WHERE account=%s AND company=%s
                        AND posting_date BETWEEN %s AND %s
                        AND is_cancelled=0
                    """, (acc.name, company, p["from_date"], p["to_date"]))
                else:
                    res = frappe.db.sql("""
                        SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0)
                        FROM `tabGL Entry`
                        WHERE account=%s AND company=%s
                        AND posting_date BETWEEN %s AND %s
                        AND is_cancelled=0
                    """, (acc.name, company, p["from_date"], p["to_date"]))

                val = frappe.utils.flt(res[0][0] if res else 0)

                row[f"p{i}"] = val
                row_total = row_total + val
                period_totals[i] = period_totals[i] + val

                if val != 0:
                    has_value = True

            row["total"] = row_total

            if show_zero_values or has_value:
                row["indent"] = 1
                rows.append(row)
                grand_total = grand_total + row_total

        return rows, period_totals, grand_total

    income_account_response = build_rows(income_accounts, "Income")
    expense_account_response = build_rows(expense_accounts, "Expense")
    
    # Unpacking
    income_rows = income_account_response[0]
    income_periods = income_account_response[1]
    total_income = income_account_response[2]
    # Unpacking
    expense_rows = expense_account_response[0]
    expense_periods = expense_account_response[1]
    total_expense = expense_account_response[2]

    # -----------------------------
    # DATA
    # -----------------------------
    data = []

    data.append({"account": "<b>Income</b>"})
    data.extend(income_rows)

    data.append({"account": "<b>Expenses</b>"})
    data.extend(expense_rows)

    # Net Profit (per period)
    net_profit_row = {"account": "<b>Net Profit</b>"}
    net_total = 0

    for i in range(len(periods)):
        val = income_periods[i] - expense_periods[i]
        net_profit_row[f"p{i}"] = val
        net_total += val

    net_profit_row["total"] = net_total
    data.append(net_profit_row)

    # -----------------------------
    # CHART
    # -----------------------------
    net_values = [income_periods[i] - expense_periods[i] for i in range(len(periods))]
    
    chart = {
        "data": {
            "labels": [p["label"] for p in periods],
            "datasets": [
                {"name": "Income", "values": [frappe.utils.flt(frappe.utils.fmt_money(val, currency=None).replace(',', '')) for val in income_periods]},
                {"name": "Expense", "values": [frappe.utils.flt(frappe.utils.fmt_money(val, currency=None).replace(',', '')) for val in expense_periods]},
                {"name": "Net Profit/Loss", "values": [frappe.utils.flt(frappe.utils.fmt_money(val, currency=None).replace(',', '')) for val in net_values]}
            ]
        },
        "type": "bar"
    }

    # -----------------------------
    # SUMMARY
    # -----------------------------
    report_summary = [
        {"label": "Net Profit", "value": frappe.utils.fmt_money(total_income - total_expense), "indicator": "Blue"},
        {"label": "Total Income", "value": frappe.utils.fmt_money(total_income), "indicator": "Green"},
        {"label": "Total Expense", "value": frappe.utils.fmt_money(total_expense), "indicator": "Red"}
    ]

    return columns, data, None, chart, report_summary


res = execute(filters)

data = res[0], res[1], res[2], res[3], res[4]
