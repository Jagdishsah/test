import streamlit as st
import pandas as pd
from github import Github, Auth
from io import StringIO
import plotly.express as px
from datetime import datetime, timedelta

## --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="NEPSE TMS Pro Ledger", 
    page_icon="💹", 
    layout="wide",
    initial_sidebar_state="expanded"
)

## --- AUTHENTICATION ---
def check_password():
    """Returns `True` if the user had the correct password."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True
    
    st.title("🔒 TMS Ledger Login")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    
    if st.button("Login"):
        try:
            ## Checks against secrets
            if user == st.secrets["auth"]["username"] and pwd == st.secrets["auth"]["password"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ Incorrect Username or Password")
        except KeyError:
            st.error("❌ Secrets not configured. Please add [auth] section to secrets.toml")
            
    return False

if not check_password():
    st.stop()


## --- 2. CUSTOM CSS FOR UI POLISH ---
st.markdown("""
<style>
    /* Metric Cards Styling */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 10px;
        border-radius: 8px;
    }
    /* Alert Box Styling */
    .risk-alert {background-color: #ffcccb; padding: 15px; border-radius: 8px; color: #8b0000; font-weight: bold; border-left: 5px solid red;}
    .safe-zone {background-color: #d4edda; padding: 15px; border-radius: 8px; color: #155724; border-left: 5px solid green;}
    /* Table Styling */
    .stDataFrame {border: 1px solid #f0f0f0; border-radius: 5px;}
</style>
""", unsafe_allow_html=True)

## --- 3. GITHUB BACKEND (DATABASE) ---
def get_repo():
    ## Tries to connect to GitHub using secrets
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        auth = Auth.Token(token)
        g = Github(auth=auth)
        return g.get_repo(repo_name)
    except:
        return None

def get_data():
    ## Fetches the CSV file from GitHub. If missing, creates an empty DataFrame.
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        file = repo.get_contents("tms_ledger_master.csv")
        df = pd.read_csv(StringIO(file.decoded_content.decode()))
        ## Convert Strings back to Date objects for math
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Due_Date"] = pd.to_datetime(df["Due_Date"]).dt.date
        return df
    except:
        ## Initialize Master Schema if file doesn't exist
        return pd.DataFrame(columns=[
            "Date", "Type", "Category", "Amount", "Status", 
            "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", 
            "Dispute_Note", "Fiscal_Year"
        ])

def get_holdings():
    repo = get_repo()
    if not repo: return pd.DataFrame(columns=["Symbol", "Total_Qty", "Pledged_Qty", "LTP", "Haircut"])
    try:
        file = repo.get_contents("tms_holdings.csv")
        return pd.read_csv(StringIO(file.decoded_content.decode()))
    except:
        return pd.DataFrame(columns=["Symbol", "Total_Qty", "Pledged_Qty", "LTP", "Haircut"])

def save_holdings(df):
    repo = get_repo()
    if not repo: return
    csv_content = df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_holdings.csv")
        repo.update_file(file.path, "Update Holdings", csv_content, file.sha)
    except:
        repo.create_file("tms_holdings.csv", "Create Holdings", csv_content)

def save_data(df):
    ## Saves the DataFrame back to GitHub CSV
    repo = get_repo()
    if not repo: return
    
    ## Create a copy to format dates as strings
    save_df = df.copy()
    save_df["Date"] = pd.to_datetime(save_df["Date"]).dt.strftime("%Y-%m-%d")
    save_df["Due_Date"] = pd.to_datetime(save_df["Due_Date"]).dt.strftime("%Y-%m-%d")
    
    csv_content = save_df.to_csv(index=False)
    try:
        file = repo.get_contents("tms_ledger_master.csv")
        repo.update_file(file.path, "Update Ledger Master", csv_content, file.sha)
    except:
        repo.create_file("tms_ledger_master.csv", "Create Ledger Master", csv_content)

## --- 4. HELPER FUNCTIONS ---
def get_fiscal_year(date_obj):
    ## Calculates Nepal Fiscal Year (starts approx mid-July / Shrawan)
    year = date_obj.year
    month = date_obj.month
    if month >= 7: return f"{year}/{year+1}"
    return f"{year-1}/{year}"

## --- 5. DATA LOGIC & CALCULATIONS (UPGRADED) ---
df = get_data()
holdings_df = get_holdings()

## Defaults (Prevents NameError on empty data)
net_cash_invested = 0.0
tms_cash_balance = 0.0
tms_balance = 0.0 # Alias for tms_cash_balance for compatibility
trading_power = 0.0
utilization_rate = 0.0
t0_due, t1_due, t2_due = 0.0, 0.0, 0.0
net_due, payable_due, receivable_due = 0.0, 0.0, 0.0
pending_df = pd.DataFrame()

if not df.empty:
    ## A. Bank & Cash Logic
    money_out = df[(df["Category"].isin(["DEPOSIT", "DIRECT_PAY", "PRIMARY_INVEST", "EXPENSE"])) & (df["Is_Non_Cash"] == False)]["Amount"].sum()
    money_in = df[df["Category"] == "WITHDRAW"]["Amount"].sum()
    net_cash_invested = money_out - money_in
    
    ## B. TMS "Cash" Balance (Ledger Balance)
    tms_credits = df[df["Category"].isin(["DEPOSIT", "RECEIVABLE", "DIRECT_PAY"])]["Amount"].sum()
    tms_debits = df[df["Category"].isin(["WITHDRAW", "PAYABLE", "EXPENSE"])]["Amount"].sum()
    tms_cash_balance = tms_credits - tms_debits
    tms_balance = tms_cash_balance # Set alias

    ## C. The "Collateral Command Center"
    ## Formula: Cash Balance + (Pledged Stock Value * (1 - Haircut/100))
    non_cash_value = 0.0
    if not holdings_df.empty:
        ## Calculate value of pledged shares
        holdings_df["Collateral_Val"] = holdings_df["Pledged_Qty"] * holdings_df["LTP"] * (1 - (holdings_df["Haircut"]/100))
        non_cash_value = holdings_df["Collateral_Val"].sum()
    
    ## Total Buying Power (Limit = Cash + NonCash_Collateral_Value)
    trading_power = tms_cash_balance + non_cash_value
    
    ## Utilization (Risk)
    ## If Ledger is negative, you are using collateral.
    used_collateral = abs(tms_cash_balance) if tms_cash_balance < 0 else 0
    utilization_rate = (used_collateral / non_cash_value * 100) if non_cash_value > 0 else 0

    ## D. T+2 Settlement Radar
    pending_df = df[df["Status"] == "Pending"].copy()
    
    ## General Net Due
    payable_due = pending_df[pending_df["Category"] == "PAYABLE"]["Amount"].sum()
    receivable_due = pending_df[pending_df["Category"] == "RECEIVABLE"]["Amount"].sum()
    net_due = payable_due - receivable_due

    if not pending_df.empty:
        today = datetime.now().date()
        pending_df["Due_Date"] = pd.to_datetime(pending_df["Due_Date"]).dt.date
        
        ## Filter by Day
        t0_df = pending_df[pending_df["Due_Date"] <= today]
        t1_df = pending_df[pending_df["Due_Date"] == today + timedelta(days=1)]
        t2_df = pending_df[pending_df["Due_Date"] >= today + timedelta(days=2)]
        
        ## Calculate Net Flow (Receivable is +, Payable is -)
        def calc_net(d): return d[d["Category"]=="RECEIVABLE"]["Amount"].sum() - d[d["Category"]=="PAYABLE"]["Amount"].sum()
        
        t0_due = calc_net(t0_df)
        t1_due = calc_net(t1_df)
        t2_due = calc_net(t2_df)


## --- 6. SIDEBAR NAVIGATION & TOOLS ---
with st.sidebar:
    st.title("💹 TMS Pro")
    
    ## Main Menu Navigation
    menu = st.radio("Navigation", [
        "🏠 Dashboard", 
        "✍️ New Entry", 
        "📜 Ledger History", 
        "📊 Analytics", 
        "🛠️ Manage Data"
    ])
    
    st.markdown("---")

    
    ## Quick Calculator Tool
    with st.expander("🧮 Quick Calc: Load Amount"):
        st.caption("How much to load to clear dues?")
        
        ## FIX: Ensure tms_balance exists and is safe
        current_bal = float(tms_balance)
        
        calc_buy = st.number_input("Todays Buy", min_value=0.0, step=1000.0)
        calc_avail = st.number_input("Avail Collateral", value=current_bal)
        
        needed = calc_buy - calc_avail
        if needed > 0:
            st.error(f"Load: Rs {needed:,.0f}")
        else:
            st.success("Covered by Collateral")
    

    ## --- SIDEBAR ADDITION: STOCK INVENTORY ---
    with st.expander("📦 Portfolio & Collateral"):
        st.caption("Manage Pledged Shares for Limit Calc")
        
        h_sym = st.text_input("Symbol", placeholder="NICA").upper()
        c1, c2 = st.columns(2)
        h_qty = c1.number_input("Pledged Qty", min_value=0)
        h_ltp = c2.number_input("LTP", min_value=0.0)
        
        if st.button("Update Stock"):
            curr_h = get_holdings()
            ## Remove existing if exists
            curr_h = curr_h[curr_h["Symbol"] != h_sym]
            ## Add new
            new_h = pd.DataFrame([{
                "Symbol": h_sym, "Total_Qty": h_qty, "Pledged_Qty": h_qty, 
                "LTP": h_ltp, "Haircut": 25 # Default 25% Haircut
            }])
            curr_h = pd.concat([curr_h, new_h], ignore_index=True)
            save_holdings(curr_h)
            st.success(f"Updated {h_sym}")
            st.rerun()
            
        if not holdings_df.empty:
            st.dataframe(holdings_df[["Symbol", "Pledged_Qty", "LTP"]], height=150)

## --- 7. MAIN PAGES ---

## >>> PAGE: DASHBOARD <<<
if menu == "🏠 Dashboard":
    st.title("🏦 Financial Command Center")
    
    ## --- DASHBOARD ROW 1: SOLVENCY & SETTLEMENT ---
    st.markdown("### 📡 T+2 Settlement Radar")
    k1, k2, k3, k4 = st.columns(4)
    
    ## 1. TODAY (Urgent)
    k1.metric(
        "📅 Today (Due)", 
        f"Rs {abs(t0_due):,.0f}", 
        delta="Pay Now" if t0_due < 0 else "Receive", 
        delta_color="inverse" if t0_due < 0 else "normal",
        help="Net Settlement amount required by EOD today."
    )
    
    ## 2. TOMORROW (Planning)
    k2.metric(
        "📆 Tomorrow (T+1)", 
        f"Rs {t1_due:,.0f}", 
        delta_color="off",
        help="Projected settlement for tomorrow."
    )
    
    ## 3. TRADING POWER (The Limit)
    k3.metric(
        "🔋 Trading Limit", 
        f"Rs {trading_power:,.0f}", 
        delta=f"{utilization_rate:.1f}% Used",
        delta_color="inverse" if utilization_rate > 90 else "normal",
        help="Cash Balance + Non-Cash Collateral Value"
    )
    
    ## 4. SOLVENCY RATIO
    ## You enter your actual bank balance manually here for the check
    bank_bal = st.number_input("Enter Bank Balance for Check:", value=0.0, label_visibility="collapsed", placeholder="Bank Balance")
    if bank_bal > 0:
        total_obligation = abs(tms_cash_balance) if tms_cash_balance < 0 else 0
        ratio = bank_bal / total_obligation if total_obligation > 0 else 999
        if ratio < 1:
            k4.error(f"⚠️ INSOLVENT (Ratio: {ratio:.2f})")
        else:
            k4.metric("🛡️ Solvency", "Safe", delta=f"{ratio:.1f}x Coverage")
    else:
        k4.metric("🛡️ Solvency", "N/A", help="Enter Bank Balance to calc")
    
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)

    ## Metric 1: Real Money Involved
    c1.metric(
        "💵 Net Cash Invested", 
        f"Rs {net_cash_invested:,.0f}", 
        help="Total Cash moved from Bank to Market. (Deposits + IPOs - Withdrawals)"
    )
    
    ## Metric 2: House Money Logic
    if net_cash_invested < 0:
        c2.metric("🏆 House Money", f"Rs {abs(net_cash_invested):,.0f}", delta="Risk Free!", help="You have withdrawn more profit than you put in!")
    else:
        c2.metric("🛡️ Capital Risk", f"Rs {net_cash_invested:,.0f}", help="Amount of your salary currently stuck in the market.")

    ## Metric 3: Broker Balance
    if tms_balance < 0:
        c3.metric("⚠️ TMS Balance", f"- Rs {abs(tms_balance):,.0f}", delta="Overdue", delta_color="inverse", help="Negative means you MUST pay the broker.")
    else:
        c3.metric("🏦 TMS Balance", f"Rs {tms_balance:,.0f}", delta="Collateral", help="Your buying power.")

    ## Metric 4: Upcoming Settlements
    c4.metric(
        "⚖️ Net Pending", 
        f"Rs {net_due:,.0f}", 
        delta=f"Pay: {payable_due:,.0f} | Rec: {receivable_due:,.0f}", 
        delta_color="inverse",
        help="Total Pending Payable - Total Pending Receivable"
    )

    st.markdown("---")

    ## Row 2: Alerts & Actions
    col_alert, col_action = st.columns([2, 1])
    
    with col_alert:
        st.subheader("🚨 Risk Monitor")
        alert_triggered = False
        
        ## Alert: Negative Balance
        if tms_balance < -50:
            st.markdown(f"<div class='risk-alert'>⚠️ URGENT: Negative Collateral of Rs {abs(tms_balance):,.2f}. Load funds or use 'Direct Payment' immediately.</div>", unsafe_allow_html=True)
            alert_triggered = True
            
        ## Alert: Overdue Settlements
        if not pending_df.empty:
            overdue = pending_df[pd.to_datetime(pending_df["Due_Date"]) < pd.to_datetime(datetime.now().date())]
            if not overdue.empty:
                st.warning(f"🕒 **{len(overdue)} Overdue Settlements!** These should have been cleared by now.")
                st.dataframe(overdue[["Date", "Type", "Amount", "Due_Date"]], height=150)
                alert_triggered = True
        
        if not alert_triggered:
            st.markdown("<div class='safe-zone'>✅ All Systems Green. No urgent risks detected.</div>", unsafe_allow_html=True)

    with col_action:
        st.subheader("⚡ Settlement Queue")
        ## Quick Action to Clear Pending Items
        if not pending_df.empty:
            opts = pending_df.apply(lambda x: f"{x['Due_Date']} | Rs {x['Amount']} ({x['Type']})", axis=1).tolist()
            sel_clear = st.multiselect("Select items settled/paid today:", opts, help="Select items where money actually left/entered your bank.")
            
            if st.button("Mark as CLEARED"):
                for item in sel_clear:
                    parts = item.split(" | ")
                    date_str = parts[0]
                    ## Extract amount carefully
                    amt_str = parts[1].split(" (")[0].replace("Rs ", "")
                    
                    ## Locate and update
                    mask = (df["Due_Date"].astype(str) == date_str) & (df["Amount"] == float(amt_str)) & (df["Status"] == "Pending")
                    idx = df[mask].first_valid_index()
                    if idx is not None:
                        df.at[idx, "Status"] = "Cleared"
                save_data(df)
                st.success("Updated!")
                st.rerun()
        else:
            st.info("Nothing pending.")

## >>> PAGE: NEW ENTRY <<<
elif menu == "✍️ New Entry":
    st.header("📝 Record New Transaction")
    
    ## Organize inputs in a clean form
    with st.form("entry_form"):
        ## Row 1: Basics
        c1, c2 = st.columns(2)
        date = c1.date_input("Transaction Date", datetime.now().date(), help="When did this happen?")
        
        ## Logic Selector
        action_cat = c2.selectbox("Transaction Category", [
            "📈 Buy/Sell Shares (TMS)",
            "🔄 Fund Transfer (Collateral)",
            "🏦 Direct Payment (EOD Settlement)",
            "🆕 IPO / Right Share",
            "⚠️ Fees / Fines / Taxes"
        ], help="Choose what you did.")
        
        ## Dynamic Inputs based on Category
        txn_type = ""
        cat = ""
        is_non_cash = False
        due_days = 0
        risk_tag = ""
        
        st.markdown("### Transaction Details")
        

        if action_cat == "📈 Buy/Sell Shares (TMS)":
            c_type = st.radio("Action", ["Buy Shares (Payable)", "Sell Shares (Receivable)"], horizontal=True)
            txn_type = c_type
            cat = "PAYABLE" if "Buy" in c_type else "RECEIVABLE"
            due_days = 2 if "Buy" in c_type else 3
            
            ## NEW: EDIS Safety Check
            if "Sell" in c_type:
                st.markdown("#### 🛡️ EDIS Safety Check")
                edis_check = st.checkbox("✅ Shares are in Demat & EDIS is ready?")
                if not edis_check:
                    st.warning("⚠️ RISK ALERT: Selling shares without EDIS confirmation risks a 20% Close-out Fine.")
                    risk_tag = "[RISK: NO EDIS] "
            
        elif action_cat == "🔄 Fund Transfer (Collateral)":
            c_type = st.radio("Action", ["Load Collateral (Deposit)", "Refund Request (Withdraw)"], horizontal=True)
            is_non_cash = st.checkbox("Non-Cash (Bank Guarantee / Cheque)", help="Check if money hasn't left bank yet.")
            txn_type = c_type
            cat = "DEPOSIT" if "Load" in c_type else "WITHDRAW"
            
        elif action_cat == "🏦 Direct Payment (EOD Settlement)":
            st.info("ℹ️ Use this when you pay Broker directly via ConnectIPS for a purchase (Bypassing Collateral Load).")
            txn_type = "Direct Payment (Bank -> Broker)"
            cat = "DIRECT_PAY" 
            
        elif action_cat == "🆕 IPO / Right Share":
            c_type = st.radio("Type", ["IPO Application", "Right Share Payment"], horizontal=True)
            txn_type = c_type
            cat = "PRIMARY_INVEST" 
            
        elif action_cat == "⚠️ Fees / Fines / Taxes":
            c_type = st.radio("Type", ["Closeout Fine (20%)", "DP Charge", "Renewal Fee"], horizontal=True)
            txn_type = c_type
            cat = "EXPENSE"

        ## Row 2: Amounts
        c3, c4, c5 = st.columns(3)
        amount = c3.number_input("Amount (Rs)", min_value=1.0, step=100.0)
        desc_input = c4.text_input("Description", placeholder="e.g. NICA, ConnectIPS, Right Share")
        ref_id = c5.text_input("Ref ID", placeholder="Cheque No / Transaction ID")
        
        ## Submit
        if st.form_submit_button("💾 Save Transaction"):
            due_date = date + timedelta(days=due_days)
            fy = get_fiscal_year(date)
            
            ## Combine Risk Tag with Description
            final_desc = risk_tag + desc_input

            ## Create Record
            new_row = pd.DataFrame([{
                "Date": date,
                "Type": txn_type,
                "Category": cat,
                "Amount": amount,
                "Status": "Pending",
                "Due_Date": due_date,
                "Ref_ID": ref_id,
                "Description": final_desc,
                "Is_Non_Cash": is_non_cash,
                "Dispute_Note": "",
                "Fiscal_Year": fy
            }])
            
            ## Append and Save
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("Entry Saved Successfully!")

## >>> PAGE: HISTORY <<<
elif menu == "📜 Ledger History":
    st.header("📜 Transaction Ledger")
    
    ## Filters Area
    with st.expander("🔍 Filter & Search", expanded=True):
        f1, f2, f3 = st.columns(3)
        search = f1.text_input("Search Text")
        cat_filter = f2.multiselect("Filter Category", df["Category"].unique() if not df.empty else [])
        stat_filter = f3.selectbox("Status", ["All", "Pending", "Cleared"])
        
    ## Apply Filters
    view_df = df.copy()
    if not view_df.empty:
        if search: view_df = view_df[view_df["Description"].str.contains(search, case=False, na=False)]
        if cat_filter: view_df = view_df[view_df["Category"].isin(cat_filter)]
        if stat_filter != "All": view_df = view_df[view_df["Status"] == stat_filter]
        
        ## Sort by Date Descending
        view_df = view_df.sort_values("Date", ascending=False)
        
        ## Visual Styling for Table
        def highlight_rows(row):
            ## Red text for Pending
            if row["Status"] == "Pending": return ["color: #d63384; font-weight: bold"] * len(row)
            return [""] * len(row)

        st.dataframe(
            view_df.style.apply(highlight_rows, axis=1).format({"Amount": "Rs {:,.2f}"}),
            use_container_width=True,
            height=600
        )
        
        ## Export
        csv = view_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download CSV", csv, "tms_ledger.csv", "text/csv")
    else:
        st.info("No records found.")

## >>> PAGE: VISUALS <<<
elif menu == "📊 Analytics":
    st.header("📊 Financial Analytics")
    
    if not df.empty:
        ## --- COST OF TRADING (CHURN) ---
        total_turnover = df[df["Category"].isin(["PAYABLE", "RECEIVABLE"])]["Amount"].sum()
        total_expenses = df[df["Category"] == "EXPENSE"]["Amount"].sum()
            
        if total_turnover > 0:
            churn_cost = (total_expenses / total_turnover) * 100
            st.metric("📉 Cost of Trading (Churn)", f"{churn_cost:.2f}%", help="Expenses as % of Total Volume. Lower is better.")
        
        tab1, tab2 = st.tabs(["📈 Cash Flow", "🍰 Portfolio Breakdown"])
        
        with tab1:
            st.subheader("Net Cash Investment Growth")
            ## Prepare Data
            cf_df = df.copy().sort_values("Date")
            ## Logic: Withdraw is Negative flow, Deposit/IPO is Positive flow
            cf_df["Flow"] = cf_df.apply(lambda x: -x["Amount"] if x["Category"] == "WITHDRAW" else (x["Amount"] if x["Category"] in ["DEPOSIT", "PRIMARY_INVEST", "DIRECT_PAY"] else 0), axis=1)
            cf_df["Cumulative"] = cf_df["Flow"].cumsum()
            
            fig_line = px.line(cf_df, x="Date", y="Cumulative", title="Net Capital Deployed Over Time", markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
            
        with tab2:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Turnover by Category")
                fig_pie = px.pie(df, values="Amount", names="Category", hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                st.subheader("Expenses & Fines")
                exp_df = df[df["Category"] == "EXPENSE"]
                if not exp_df.empty:
                    fig_exp = px.bar(exp_df, x="Type", y="Amount", color="Type")
                    st.plotly_chart(fig_exp, use_container_width=True)
                else:
                    st.info("No expenses recorded.")
    else:
        st.warning("No data available to visualize.")

## >>> PAGE: MANAGE DATA <<<
elif menu == "🛠️ Manage Data":
    st.header("🛠️ Data Management")
    st.info("Use this section to correct mistakes or add notes to disputes.")
    
    ## Select Box Logic
    ## Create a label that is easy to read
    if not df.empty:
        df["Label"] = df.apply(lambda x: f"{x['Date']} | {x['Category']} | Rs {x['Amount']} | {x['Description']}", axis=1)
        
        sel_label = st.selectbox("Select Transaction to Edit/Delete", df["Label"].tolist())
        
        if sel_label:
            ## Get Index
            idx = df[df["Label"] == sel_label].index[0]
            row = df.loc[idx]
            
            st.write("---")
            st.write(f"**Selected:** {row['Type']} on {row['Date']}")
            
            c_edit, c_del = st.columns(2)
            
            with c_edit:
                st.subheader("📝 Edit Dispute / Note")
                curr_note = row["Dispute_Note"] if pd.notna(row["Dispute_Note"]) else ""
                new_note = st.text_input("Add Note (e.g., 'Called Broker')", value=curr_note)
                
                if st.button("Update Note"):
                    df.at[idx, "Dispute_Note"] = new_note
                    save_data(df)
                    st.success("Note updated.")
                    st.rerun()
            
            with c_del:
                st.subheader("🗑️ Delete Transaction")
                st.warning("Action is permanent.")
                if st.button("DELETE PERMANENTLY"):
                    df = df.drop(index=idx)
                    save_data(df)
                    st.error("Deleted.")
                    st.rerun()
    else:
        st.write("No data to manage.")
