def execute(filters=None):
    filters = filters or {}
    
    company   = filters.get("company")
    periodicity = filters.get("periodicity") or "Yearly"
    show_zero_values = int(filters.get("show_zero_values") or 0)
    
    # -----------------------------
    # GET / DEFAULT FISCAL YEAR
    # -----------------------------
    fiscal_year = filters.get("fiscal_year")
    
    #  Step 1: Try default fiscal year
    if not fiscal_year:
        fiscal_year = frappe.db.get_value("Fiscal Year", {"is_default": 1}, "name")
    
    #  Step 2: Fallback to current date match
    if not fiscal_year:
        fiscal_year = frappe.db.sql("""
            SELECT name
            FROM `tabFiscal Year`
            WHERE %s BETWEEN year_start_date AND year_end_date
            LIMIT 1
        """, frappe.utils.today())[0][0]
    
    #  Final safety
    if not fiscal_year:
        frappe.throw("No Fiscal Year found")
    
    # -----------------------------
    # GET FISCAL YEAR DATES
    # -----------------------------
    fy = frappe.db.get_value(
        "Fiscal Year",
        fiscal_year,
        ["year_start_date", "year_end_date"],
        as_dict=True
    )
    
    if not fy:
        frappe.throw("Invalid Fiscal Year")
    
    from_date = fy.year_start_date
    to_date = fy.year_end_date
    
    # -----------------------------
    # VALIDATIONS
    # -----------------------------
    if not company:
        frappe.throw("Company is required")
    
    if not from_date or not to_date:
        frappe.throw("From Date and To Date are required")
        # -----------------------------
    # 1. BUILD PERIODS
    # -----------------------------
    def get_periods(from_date, to_date, periodicity):
        periods = []
        month_map = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        current = frappe.utils.getdate(from_date)
        end     = frappe.utils.getdate(to_date)

        step = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6}.get(periodicity, 12)

        while current <= end:
            start = current
            next_date = frappe.utils.add_months(start, step)
            end_d = frappe.utils.add_days(next_date, -1)
            if end_d > end:
                end_d = end

            label = (month_map[start.month - 1] + " " + str(start.year)
                     if periodicity == "Monthly"
                     else f"{month_map[start.month - 1]}{start.year}-{month_map[end_d.month - 1]}{end_d.year}")

            periods.append({
                "from_date": start,
                "to_date": end_d,
                "label": label
            })
            current = next_date
        return periods

    periods = get_periods(from_date, to_date, periodicity)

    # -----------------------------
    # 2. COLUMNS
    # -----------------------------
    columns = [{"label": "Account", "fieldname": "account", "fieldtype": "Data", "width": 300}]
    for i, p in enumerate(periods):
        columns.append({"label": p["label"], "fieldname": f"p{i}", "fieldtype": "Currency", "width": 150})
    columns.append({"label": "Total", "fieldname": "total", "fieldtype": "Currency", "width": 150})

    # -----------------------------
    # 3. GET ACCOUNTS
    # -----------------------------
    def get_accounts(root_type):
        return frappe.db.get_all("Account",
            filters={"company": company, "root_type": root_type, "is_group": 0},
            fields=["name", "account_name", "account_number"]
        )

    assets = get_accounts("Asset")
    liabilities = get_accounts("Liability")
    equity = get_accounts("Equity")

    # -----------------------------
    # 4. GET BALANCE
    # -----------------------------
    def get_balance(account_name, root_type, end_date):
        if root_type == "Asset":
            res = frappe.db.sql("""
                SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s
                AND posting_date <= %s
                AND is_cancelled=0
            """, (account_name, company, end_date))
        else:  # Liability & Equity
            res = frappe.db.sql("""
                SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0)
                FROM `tabGL Entry`
                WHERE account=%s AND company=%s
                AND posting_date <= %s
                AND is_cancelled=0
            """, (account_name, company, end_date))

        return frappe.utils.flt(res[0][0] if res else 0)

    # -----------------------------
    # 5. BUILD ROWS
    # -----------------------------
    def build_rows(accounts, root_type):
        rows = []
        totals = [0] * len(periods)
    
        for acc in accounts:
            row = {
                "display_name": f"{acc.get('account_number') or ''} {acc.get('account_name')}",
                "account_name": acc.get("name"),
                "account": f"{acc.get('account_number') or ''} {acc.get('account_name')}",
            }
    
            row_total = 0
            has_value = False
            prev_balance = 0  
    
            for i, p in enumerate(periods):
                current_balance = get_balance(acc["name"], root_type, p["to_date"])
    
                # PERIOD VALUE 
                period_value = current_balance - prev_balance
    
                prev_balance = current_balance  # update for next loop
    
                row[f"p{i}"] = period_value
                row_total = row_total + period_value
                totals[i] = totals[i] + period_value
    
                if period_value != 0:
                    has_value = True
    
            row["total"] = row_total
    
            if show_zero_values or has_value:
                row["indent"] = 1
                rows.append(row)
    
        return rows, totals
    # -----------------------------
    # 6. ADD SECTIONS
    # -----------------------------
    data = []

    def add_section(title, accounts, root_type):
        rows_and_totals = build_rows(accounts, root_type)
        rows = rows_and_totals[0]
        totals = rows_and_totals[1]
        total_row = {"account": f"<b>{title}</b>"}
        total_sum = 0
        for i, t in enumerate(totals):
            total_row[f"p{i}"] = t
            total_sum = total_sum + t
        total_row["total"] = total_sum

        data.append(total_row)
        data.extend(rows)
        return totals

    asset_totals = add_section("Assets", assets, "Asset")
    liability_totals = add_section("Liabilities", liabilities, "Liability")
    equity_totals = add_section("Equity", equity, "Equity")

    # -----------------------------
    # 7. CHECK BALANCE ROW
    # -----------------------------
    check_row = {"account": "<b>Check (A - L - E)</b>"}
    diff_values = []
    for i in range(len(periods)):
        diff = asset_totals[i] - (liability_totals[i] + equity_totals[i])
        check_row[f"p{i}"] = diff
        diff_values.append(diff)
    check_row["total"] = sum(diff_values)
    data.append(check_row)

    # -----------------------------
    # 8. CHART DATA
    # -----------------------------
    labels = [p["label"] for p in periods]
    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Assets", "values": asset_totals},
                {"name": "Liabilities", "values": liability_totals},
                {"name": "Equity", "values": equity_totals}
            ]
        },
        "type": "bar"
    }

    # -----------------------------
    # 9. REPORT SUMMARY
    # -----------------------------
    report_summary = [
    {
        "label": "Total Assets",
        "value": frappe.utils.fmt_money(sum(asset_totals), currency=None),
        "indicator": "Green"
    },
    {
        "label": "Total Liabilities",
        "value": frappe.utils.fmt_money(sum(liability_totals), currency=None),
        "indicator": "Red"
    },
    {
        "label": "Total Equity",
        "value": frappe.utils.fmt_money(sum(equity_totals), currency=None),
        "indicator": "Blue"
    }
]

    return columns, data, None, chart, report_summary
res = execute(filters)
data = res[0], res[1], res[2], res[3], res[4]
