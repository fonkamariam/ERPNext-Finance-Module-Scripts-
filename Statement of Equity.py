def execute(filters=None):
    filters = dict(filters or {})

    if not filters.get("from_date"):
        filters["from_date"] = frappe.utils.add_days(frappe.utils.today(), -365)
    if not filters.get("to_date"):
        filters["to_date"] = frappe.utils.today()

    company = filters.get("company")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    periodicity = filters.get("periodicity") or "Yearly"  # Default to yearly

    if not all([company, from_date, to_date]):
        frappe.throw("Please select Company, From Date, and To Date")

    company_currency = "ETB"  # Change if your company uses different currency

    # ── 1. Compute periods based on periodicity ──────────────────────────────
    def get_periods(from_date, to_date, periodicity):
        periods = []
    
        month_map = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
        current = frappe.utils.getdate(from_date)
        end     = frappe.utils.getdate(to_date)
    
        # step size
        if periodicity == "Monthly":
            step = 1
        elif periodicity == "Quarterly":
            step = 3
        elif periodicity == "Half-Yearly":
            step = 6
        else:
            step = 12
    
        while current <= end:
    
            start = current
            next_date = frappe.utils.add_months(start, step)
            end_d = frappe.utils.add_days(next_date, -1)
    
            # clamp to overall range
            if end_d > end:
                end_d = end
    
            # LABEL FIX (ERP STYLE)
            start_label = month_map[start.month - 1] + str(start.year)[-2:]
            end_label   = month_map[end_d.month - 1] + str(end_d.year)[-2:]
    
            if periodicity == "Monthly":
                label = month_map[start.month - 1] + " " + str(start.year)[-2:]
            else:
                label = start_label + "-" + end_label
    
            periods.append({
                "from_date": start,
                "to_date": end_d,
                "label": label
            })
    
            current = next_date
    
        return periods
    periods = get_periods(from_date, to_date, periodicity)

    # ── 2. Prepare dynamic columns ───────────────────────────────────────────
    columns = [
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 400}
    ]
    for i, p in enumerate(periods):
        columns.append({
            "label": p["label"],
            "fieldname": f"p{i}",
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150
        })
    columns.append({
        "label": _("Total"),
        "fieldname": "total",
        "fieldtype": "Currency",
        "options": company_currency,
        "width": 150
    })

    data = []

    # ── 3. Fetch Equity accounts once ─────────────────────────────────────────
    equity_accounts = frappe.db.get_all("Account",
        filters={"company": company, "root_type": "Equity", "is_group": 0},
        fields=["name", "account_name"],
        order_by="account_name"
    )

    # ── Helper: compute balances per account per period ──────────────────────
    def build_rows(accounts, keyword_filters=None, income_expense=""):
        rows = []
        total_all = 0
        for acc in accounts:
            account_name = acc.account_name or acc.name
            if keyword_filters:
                if not any(kw in account_name.lower() for kw in keyword_filters):
                    continue
            row = {"account": account_name, "account_name": acc.name}
            row_total = 0
            has_value = False
            for i, p in enumerate(periods):
                if income_expense == "Income":
                    res = frappe.db.sql("""
                        SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                        FROM `tabGL Entry`
                        WHERE account=%s AND company=%s
                        AND posting_date >= %s AND posting_date <= %s
                        AND is_cancelled=0
                    """, (acc.name, company, p["from_date"], p["to_date"]))
                elif income_expense == "Expense":
                    res = frappe.db.sql("""
                        SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0)
                        FROM `tabGL Entry`
                        WHERE account=%s AND company=%s
                        AND posting_date >= %s AND posting_date <= %s
                        AND is_cancelled=0
                    """, (acc.name, company, p["from_date"], p["to_date"]))
                else:
                    res = frappe.db.sql("""
                        SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                        FROM `tabGL Entry`
                        WHERE account=%s AND company=%s
                        AND posting_date >= %s AND is_cancelled=0
                    """, (acc.name, company, p["from_date"]))

                val = frappe.utils.flt(res[0][0] if res else 0)
                row[f"p{i}"] = val
                row_total += val
                if val != 0:
                    has_value = True
            if has_value:
                row["total"] = row_total
                rows.append(row)
                total_all += row_total
        return rows, total_all

    # ── 4. Beginning Retained Earnings ───────────────────────────────────────
    beginning_rows = build_rows(equity_accounts, ["retain", "retain earning"])[0]
    beginning_total = build_rows(equity_accounts, ["retain", "retain earning"])[1]
    
    
    data.append({"account": "<b>Beginning Retained Earnings</b>", "total": beginning_total, "indent": 0})
    # Child rows now with indent
    for row in beginning_rows:
        row["indent"] = 1
        data.append(row)

    # ── 5. Net Income ────────────────────────────────────────────────────────
    income_accounts = frappe.db.get_all("Account",
        filters={"company": company, "root_type": "Income", "is_group": 0},
        fields=["name", "account_name"]
    )
    expense_accounts = frappe.db.get_all("Account",
        filters={"company": company, "root_type": "Expense", "is_group": 0},
        fields=["name", "account_name"]
    )

    income_rows = build_rows(income_accounts, income_expense="Income")[0]
    net_income_total = build_rows(income_accounts, income_expense="Income")[1]
    expense_rows = build_rows(expense_accounts, income_expense="Expense")[0]
    expense_total = build_rows(expense_accounts, income_expense="Expense")[1]

    # Combine Net Income
    net_income_section = []
    for r in income_rows + expense_rows:
        # Keep indent for child rows
        net_row = {"account": r["account"],"account_name": r.get("account_name"), "total": r.get("total", 0), "indent": 1}
        # Add dynamic period columns
        for k in r:
            if k.startswith("p"):
                net_row[k] = r[k]
        net_income_section.append(net_row)
    
    net_income_total = net_income_total - expense_total
    data.append({"account": "<b>Net Income</b>", "total": net_income_total, "indent": 0})
    data.extend(net_income_section)

    # ── 6. Dividends ────────────────────────────────────────────────────────
    dividends_rows = build_rows(equity_accounts, ["dividend", "drawing", "distribution", "withdrawal", "owner"], None)[0]
    dividends_total = build_rows(equity_accounts, ["dividend", "drawing", "distribution", "withdrawal", "owner"], None)[1]
    data.append({"account": "<b>Dividends</b>", "total": -dividends_total, "indent": 0})
    for row in dividends_rows:
        row["indent"] = 1
        data.append(row)
    # ── 7. Ending Retained Earnings ─────────────────────────────────────────
    calculated_ending = beginning_total + net_income_total - dividends_total
    data.append({"account": "<b>Ending Retained Earnings (calculated)</b>", "total": calculated_ending, "indent": 0})
    
    # --- 8. Chart for the report ---
    # We'll create a column chart where X-axis = periods, Y-axis = amounts
    # The chart will auto-adjust to periodicity (monthly/quarterly/half-yearly/yearly)

    chart = {
        "data": {
            "labels": [],  # period labels
            "datasets": [
                {"name": "Beginning Retained Earnings", "values": []},
                {"name": "Net Income", "values": []},
                {"name": "Dividends", "values": []},
                {"name": "Ending Retained Earnings", "values": []}
            ]
        },
        "type": "bar",  # you can use "line" if you prefer
        "title": "Equity Summary",
        "height": 300
    }
    
    # Use the get_periods function to get periods for current filter
    periods = get_periods(from_date, to_date, filters.get("periodicity") or "Yearly")
    
    for p in periods:
        chart["data"]["labels"].append(p["label"])
    
        # Calculate totals per period
        # Beginning Retained Earnings (before period start)
        bre_total = 0
        for acc in equity_accounts:
            if "retain" not in (acc.account_name or acc.name).lower():
                continue
            bal_res = frappe.db.sql("""
                SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s AND posting_date < %s AND is_cancelled=0
            """, (acc.name, company, p["from_date"]))
            bal = frappe.utils.flt(bal_res[0][0] if bal_res and bal_res[0] else 0.0)
            bre_total += bal
    
        # Net Income
        net_total = 0
        for acc in income_accounts:
            bal_res = frappe.db.sql("""
                SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s AND posting_date >= %s AND posting_date <= %s AND is_cancelled=0
            """, (acc.name, company, p["from_date"], p["to_date"]))
            net_total += frappe.utils.flt(bal_res[0][0] if bal_res and bal_res[0] else 0.0)
    
        for acc in expense_accounts:
            bal_res = frappe.db.sql("""
                SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s AND posting_date >= %s AND posting_date <= %s AND is_cancelled=0
            """, (acc.name, company, p["from_date"], p["to_date"]))
            net_total -= frappe.utils.flt(bal_res[0][0] if bal_res and bal_res[0] else 0.0)
    
        # Dividends
        div_total = 0
        for acc in equity_accounts:
            name = acc.account_name or acc.name
            if not any(kw in name.lower() for kw in ["dividend", "drawing", "distribution", "withdrawal", "owners withdrawal"]):
                continue
            bal_res = frappe.db.sql("""
                SELECT COALESCE(SUM(debit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s AND posting_date >= %s AND posting_date <= %s AND is_cancelled=0
            """, (acc.name, company, p["from_date"], p["to_date"]))
            div_total += frappe.utils.flt(bal_res[0][0] if bal_res and bal_res[0] else 0.0)
    
        # Ending Retained Earnings = Beginning + Net Income - Dividends
        ending_total = bre_total + net_total - div_total
    
        # Append values to chart datasets
        chart["data"]["datasets"][0]["values"].append(bre_total)
        chart["data"]["datasets"][1]["values"].append(net_total)
        chart["data"]["datasets"][2]["values"].append(div_total)
        chart["data"]["datasets"][3]["values"].append(ending_total)
    
    # ── 9. Report Summary ───────────────────────────────────────────────────
    report_summary = [
        {"label": "Beginning Retained Earnings", "value": beginning_total, "datatype": "Currency", "currency": company_currency, "indicator": "Blue"},
        {"label": "Net Income", "value": net_income_total, "datatype": "Currency", "currency": company_currency, "indicator": "Green" if net_income_total >= 0 else "Red"},
        {"label": "Dividends", "value": dividends_total, "datatype": "Currency", "currency": company_currency, "indicator": "Red"},
        {"label": "Ending Retained Earnings", "value": calculated_ending, "datatype": "Currency", "currency": company_currency, "indicator": "Blue" if calculated_ending >= 0 else "Red"},
    ]

    return columns, data, None, chart, report_summary
res = execute(filters)

data = res[0], res[1], res[2], res[3], res[4]
