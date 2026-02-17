import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from github import Github
from io import StringIO
import plotly.express as px
from datetime import datetime
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Pro Terminal", page_icon="📈", layout="wide")

# Constants
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {background-color: #0E1117; border: 1px solid #262730; padding: 15px; border-radius: 5px; margin-bottom: 10px;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .success-text {color: #00FF00;}
    .danger-text {color: #FF4B4B;}
    div.block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# --- GITHUB ENGINE ---
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        g = Github(token)
        return g.get_user().get_repo(repo_name)
    except:
        st.error("GitHub Connection Failed. Check Secrets.")
        return None

def get_data(filename):
    repo = get_repo()
    if not repo: return pd.DataFrame()
    
    # Define Schemas
    try:
        file = repo.get_contents(filename)
        return pd.read_csv(StringIO(file.decoded_content.decode()))
    except:
        # Return empty DF with correct columns if file missing
        if "portfolio" in filename:
            cols = ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Buy_Date", "Stop_Loss", "Notes"]
        elif "watchlist" in filename:
            cols = ["Symbol", "Target", "Condition", "Note"]
        elif "history" in filename:
            cols = ["Date", "Buy_Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Invested_Amount", "Received_Amount", "Net_PL", "PL_Pct", "Reason"]
        elif "cache" in filename:
            cols = ["Symbol", "LTP", "Change", "High52", "Low52", "LastUpdated"]
        elif "wealth_log" in filename: # Tracks Net Worth over time
            cols = ["Date", "Total_Equity", "Cash_In_Hand", "Net_Worth"]
        elif "data" in filename: # Tracks Realized/Unrealized P/L over time
            cols = ["Date", "Realized_PL", "Unrealized_PL", "Total_PL"]
        elif "price_log" in filename: # Tracks Price history for Change calc
            cols = ["Date", "Symbol", "LTP"]
        elif "activity_log" in filename: # Audit Trail
            cols = ["Timestamp", "Category", "Symbol", "Action", "Details", "Amount"]
        else:
            return pd.DataFrame()
        return pd.DataFrame(columns=cols)

def save_data(filename, df):
    repo = get_repo()
    if not repo: return
    
    csv_content = df.to_csv(index=False)
    try:
        file = repo.get_contents(filename)
        repo.update_file(file.path, f"Update {filename}", csv_content, file.sha)
    except:
        repo.create_file(filename, f"Create {filename}", csv_content)

# --- LOGGER ENGINE ---
def log_activity(category, symbol, action, details, amount=0.0):
    """
    Logs an event to activity_log.csv
    Category: TRADE, ALERT, SYSTEM, NOTE
    Action: BUY, SELL, STOP_LOSS, TARGET, UPDATE
    """
    log = get_data("activity_log.csv")
    
    # Nepal Time
    now_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
    
    new_entry = pd.DataFrame([{
        "Timestamp": now_str,
        "Category": category,
        "Symbol": symbol,
        "Action": action,
        "Details": details,
        "Amount": amount
    }])
    
    log = pd.concat([new_entry, log], ignore_index=True)
    save_data("activity_log.csv", log)

# --- MARKET DATA ENGINE ---
def fetch_live_single(symbol):
    try:
        url = f"https://www.sharesansar.com/company/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # Scrape Logic (Adjust selectors if Sharesansar changes)
        price_txt = soup.select_one(".current-price").text.replace(",", "")
        
        # Safe extraction for range
        try:
            range_txt = soup.select("div.company-transact-price-range span")[1].text
            low, high = map(float, range_txt.split("-"))
        except:
            low, high = 0, 0
            
        return {
            'price': float(price_txt),
            'high': high,
            'low': low
        }
    except:
        return {'price': 0, 'high': 0, 'low': 0}

def update_wealth_log(port, cache):
    # This tracks TOTAL PORTFOLIO VALUE (Net Worth)
    if port.empty or cache.empty: return
    
    df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    current_val = (df["Units"] * df["LTP"]).sum()
    
    w_log = get_data("wealth_log.csv")
    today = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d")
    
    if w_log.empty or w_log.iloc[-1]["Date"] != today:
        new_row = pd.DataFrame([{
            "Date": today,
            "Total_Equity": current_val,
            "Cash_In_Hand": 0, # Placeholder for future Feature
            "Net_Worth": current_val
        }])
        w_log = pd.concat([w_log, new_row], ignore_index=True)
        save_data("wealth_log.csv", w_log)

def update_data_log(port, hist, cache):
    # This tracks REALIZED vs UNREALIZED P/L
    if port.empty or cache.empty: return

    # 1. Calculate Unrealized
    df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    # If LTP is 0 (scrape failed), fallback to WACC to avoid huge losses in chart
    df["LTP"] = df.apply(lambda x: x["WACC"] if x["LTP"] == 0 else x["LTP"], axis=1)
    
    curr_val = (df["Units"] * df["LTP"]).sum()
    curr_cost = df["Total_Cost"].sum()
    unrealized = curr_val - curr_cost

    # 2. Calculate Realized (Cumulative)
    realized = 0
    if not hist.empty:
        realized = hist["Net_PL"].sum()

    # 3. Save
    d_log = get_data("data.csv")
    today = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d")

    if d_log.empty or d_log.iloc[-1]["Date"] != today:
        new_row = pd.DataFrame([{
            "Date": today,
            "Realized_PL": realized,
            "Unrealized_PL": unrealized,
            "Total_PL": realized + unrealized
        }])
        d_log = pd.concat([d_log, new_row], ignore_index=True)
        save_data("data.csv", d_log)

def refresh_market_cache():
    port = get_data("portfolio.csv")
    watch = get_data("watchlist.csv")
    price_log = get_data("price_log.csv")
    hist = get_data("history.csv")
    
    symbols = set(port["Symbol"].tolist() + watch["Symbol"].tolist())
    if not symbols: return
    
    cache_list = []
    new_log_entries = []
    
    progress = st.progress(0, "Connecting to Market...")
    now_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M")
    
    for i, sym in enumerate(symbols):
        progress.progress((i+1)/len(symbols), f"Fetching {sym}...")
        live = fetch_live_single(sym)
        current_ltp = live['price']
        
        # --- SMART CHANGE LOGIC ---
        calculated_change = 0.0
        
        if not price_log.empty:
            sym_hist = price_log[price_log["Symbol"] == sym]
        else:
            sym_hist = pd.DataFrame()

        if not sym_hist.empty:
            last_stored_ltp = float(sym_hist.iloc[-1]["LTP"])
            if current_ltp != last_stored_ltp:
                calculated_change = current_ltp - last_stored_ltp
                new_log_entries.append({"Date": now_str, "Symbol": sym, "LTP": current_ltp})
            else:
                if len(sym_hist) >= 2:
                    prev_stored_ltp = float(sym_hist.iloc[-2]["LTP"])
                    calculated_change = current_ltp - prev_stored_ltp
        else:
            new_log_entries.append({"Date": now_str, "Symbol": sym, "LTP": current_ltp})
        
        cache_list.append({
            "Symbol": sym, "LTP": current_ltp, "Change": calculated_change,
            "High52": live['high'], "Low52": live['low'], "LastUpdated": now_str
        })
        time.sleep(0.1)
        
    progress.empty()
    
    # Save Files
    new_cache = pd.DataFrame(cache_list)
    save_data("cache.csv", new_cache)
    
    if new_log_entries:
        price_log = pd.concat([price_log, pd.DataFrame(new_log_entries)], ignore_index=True)
        save_data("price_log.csv", price_log)
    
    # Update Background Logs
    update_wealth_log(port, new_cache)
    update_data_log(port, hist, new_cache)
    
    st.toast("Market Data & Logs Updated!", icon="✅")
    st.cache_data.clear()

def calculate_metrics(units, cost, current_price, tax_rate=CGT_SHORT):
    market_val = units * current_price
    gross_pl = market_val - cost
    
    # Sell Taxes
    commission = market_val * 0.004 # Approx broker comm
    sebon = market_val * SEBON_FEE
    dp = DP_CHARGE
    
    net_sell_val = market_val - commission - sebon - dp
    
    # CGT
    taxable = net_sell_val - cost
    tax = taxable * tax_rate if taxable > 0 else 0
    
    net_pl = taxable - tax
    ret_pct = (net_pl / cost * 100) if cost > 0 else 0
    
    return market_val, net_pl, ret_pct, (market_val - cost) # Returns raw diff for day change

# --- SIDEBAR ---
with st.sidebar:
    st.title("🐯 NEPSE Pro")
    menu = st.radio("Menu", ["Dashboard", "Portfolio Manager", "Watchlist", "Activity Log", "Manage Data", "Data Analysis"])
    st.markdown("---")
    if st.button("🔄 Refresh Market Data"):
        refresh_market_cache()

# ================= DASHBOARD =================
if menu == "Dashboard":
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    hist = get_data("history.csv")
    
    if not port.empty and not cache.empty:
        df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    else:
        df = port.copy() if not port.empty else pd.DataFrame()
        if not df.empty: df["LTP"] = 0

    last_up = cache["LastUpdated"].iloc[0] if not cache.empty else "Never"
    st.title("📊 Market Dashboard")
    st.caption(f"Last Updated: {last_up}")

    if df.empty:
        st.info("Portfolio is empty. Start by adding trades.")
    else:
        # A. Current Holdings (Unrealized)
        curr_inv = df["Total_Cost"].sum()
        curr_val = 0
        day_change = 0
        alerts = []
        
        sector_data = {}
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            val = row["Units"] * ltp
            d_chg = row["Units"] * row.get("Change", 0)
            curr_val += val
            day_change += d_chg
            
            sec = row.get("Sector", "Unclassified")
            sector_data[sec] = sector_data.get(sec, 0) + val
            
            sl = row.get("Stop_Loss", 0)
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT:** {row['Symbol']} @ {ltp} (SL: {sl})")
        
        curr_pl = curr_val - curr_inv
        curr_ret = (curr_pl / curr_inv * 100) if curr_inv else 0

        # B. Closed Holdings (Realized)
        realized_pl = 0
        realized_inv = 0
        realized_recv = 0
        if not hist.empty:
            realized_pl = hist["Net_PL"].sum()
            if "Invested_Amount" in hist.columns:
                realized_inv = hist["Invested_Amount"].sum()
                realized_recv = hist["Received_Amount"].sum()
            elif "Buy_Price" in hist.columns:
                realized_inv = (hist["Units"] * hist["Buy_Price"]).sum()
                realized_recv = (hist["Units"] * hist["Sell_Price"]).sum()

        realized_ret = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0

        # C. Lifetime Stats
        lifetime_invested = curr_inv + realized_inv
        lifetime_received = realized_recv 
        net_exposure = lifetime_received - lifetime_invested 

        # --- DISPLAY ---
        st.markdown("### 🏦 Net Worth Snapshot")
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Portfolio Value", f"Rs {curr_val:,.0f}")
        m2.metric("Total Active Investment", f"Rs {curr_inv:,.0f}")
        m3.metric("Today's Change", f"Rs {day_change:,.0f}", delta=day_change)
        
        st.markdown("---")
        
        st.markdown("### ⚖️ Profit/Loss Analysis")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Net Realized P/L", f"Rs {realized_pl:,.0f}", delta=f"{realized_ret:.2f}%")
        c2.metric("📈 Unrealized P/L", f"Rs {curr_pl:,.0f}", delta=f"{curr_ret:.2f}%")
        c3.metric("🏆 Lifetime P/L", f"Rs {realized_pl + curr_pl:,.0f}", help="Realized + Unrealized")
        
        best_stock = "-"
        if not hist.empty:
            best_trade = hist.loc[hist["Net_PL"].idxmax()]
            best_stock = f"{best_trade['Symbol']} (+{best_trade['Net_PL']:.0f})"
        c4.metric("🥇 Best Trade", best_stock)

        st.markdown("---")

        st.markdown("### 💼 Investment Cycle (Lifetime)")
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Total Capital Deployed", f"Rs {lifetime_invested:,.0f}", help="Sum of all money ever invested.")
        i2.metric("Total Cash Recycled", f"Rs {lifetime_received:,.0f}", help="Total money returned from sales.")
        i3.metric("Net Cash Flow", f"Rs {net_exposure:,.0f}", help="Positive = You took out profit. Negative = Money still in market.")
        
        turnover = (realized_inv / curr_inv * 100) if curr_inv else 0
        i4.metric("Capital Turnover", f"{turnover:.1f}%")

        st.markdown("---")
        
        col_chart, col_alert = st.columns([2, 1])
        with col_chart:
            st.subheader("Sector Allocation")
            sec_df = pd.DataFrame(list(sector_data.items()), columns=["Sector", "Value"])
            if not sec_df.empty:
                fig = px.pie(sec_df, values="Value", names="Sector", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
                
        with col_alert:
            st.subheader("📢 Alerts")
            if alerts:
                for a in alerts: st.error(a)
            else:
                st.info("System Normal.")
                
            wl = get_data("watchlist.csv")
            if not wl.empty and not cache.empty:
                wl_m = pd.merge(wl, cache, on="Symbol", how="left")
                hits = wl_m[(wl_m["LTP"] <= wl_m["Target"]) & (wl_m["LTP"] > 0)]
                if not hits.empty:
                    st.markdown("---")
                    for _, h in hits.iterrows():
                        st.success(f"🎯 **BUY:** {h['Symbol']} @ {h['LTP']}")

# ================= PORTFOLIO MANAGER =================
elif menu == "Portfolio Manager":
    st.title("💼 Portfolio Manager")
    
    tab1, tab2 = st.tabs(["Add Trade", "Sell Stock"])
    
    with tab1:
        with st.form("add_trade"):
            sym = st.text_input("Symbol (e.g., NICA)").upper()
            units = st.number_input("Units", min_value=1)
            price = st.number_input("Purchase Price (WACC)", min_value=1.0)
            sector = st.selectbox("Sector", ["Banking", "Hydro", "Finance", "Insurance", "Others"])
            date = st.date_input("Date")
            sl = st.number_input("Stop Loss", min_value=0.0)
            note = st.text_area("Notes")
            
            if st.form_submit_button("Add Trade"):
                port = get_data("portfolio.csv")
                total = units * price
                
                # Check for averaging
                if not port.empty and sym in port["Symbol"].values:
                    exist = port[port["Symbol"] == sym].iloc[0]
                    old_u = exist["Units"]
                    old_c = exist["Total_Cost"]
                    
                    new_u = old_u + units
                    new_c = old_c + total
                    new_wacc = new_c / new_u
                    
                    port.loc[port["Symbol"] == sym, ["Units", "Total_Cost", "WACC", "Stop_Loss"]] = [new_u, new_c, new_wacc, sl]
                    st.info(f"Averaged {sym}. New WACC: {new_wacc:.2f}")
                else:
                    new_row = pd.DataFrame([{
                        "Symbol": sym, "Sector": sector, "Units": units, 
                        "Total_Cost": total, "WACC": price, "Buy_Date": date, 
                        "Stop_Loss": sl, "Notes": note
                    }])
                    port = pd.concat([port, new_row], ignore_index=True)
                
                save_data("portfolio.csv", port)
                log_activity("TRADE", sym, "BUY", f"Added/Averaged {units} units @ Rs {price}", -total)
                st.success(f"Added {sym} to Portfolio!")

    with tab2:
        port = get_data("portfolio.csv")
        cache = get_data("cache.csv")
        if not port.empty:
            sel_sym = st.selectbox("Select Stock to Sell", port["Symbol"].unique())
            row = port[port["Symbol"] == sel_sym].iloc[0]
            
            # Auto-fill LTP
            curr_p = 0
            if not cache.empty and sel_sym in cache["Symbol"].values:
                curr_p = cache[cache["Symbol"] == sel_sym].iloc[0]["LTP"]
            
            st.info(f"Holding: {row['Units']} Units | WACC: {row['WACC']:.2f} | LTP: {curr_p}")
            
            with st.form("sell_form"):
                u_sell = st.number_input("Units to Sell", 1, int(row['Units']))
                p_sell = st.number_input("Selling Price", min_value=1.0, value=float(curr_p))
                reason = st.text_input("Reason for Exit")
                
                if st.form_submit_button("Execute Sell"):
                    # Calculate Metrics
                    cost_basis = u_sell * row["WACC"]
                    m_val, net_pl, ret, _ = calculate_metrics(u_sell, cost_basis, p_sell)
                    received_amt = m_val - (m_val * 0.004) - (m_val * SEBON_FEE) - DP_CHARGE - (net_pl * CGT_SHORT if net_pl > 0 else 0)

                    # Update Portfolio
                    if u_sell == row['Units']:
                        port = port[port["Symbol"] != sel_sym]
                    else:
                        port.loc[port["Symbol"] == sel_sym, "Units"] -= u_sell
                        port.loc[port["Symbol"] == sel_sym, "Total_Cost"] -= cost_basis
                    
                    save_data("portfolio.csv", port)
                    
                    # Update History
                    hist = get_data("history.csv")
                    new_hist = pd.DataFrame([{
                        "Date": datetime.now().strftime("%Y-%m-%d"),
                        "Buy_Date": row["Buy_Date"],
                        "Symbol": sel_sym,
                        "Units": u_sell,
                        "Buy_Price": row["WACC"],
                        "Sell_Price": p_sell,
                        "Invested_Amount": cost_basis,
                        "Received_Amount": received_amt,
                        "Net_PL": net_pl,
                        "PL_Pct": ret,
                        "Reason": reason
                    }])
                    hist = pd.concat([new_hist, hist], ignore_index=True)
                    save_data("history.csv", hist)
                    
                    log_activity("TRADE", sel_sym, "SELL", f"Sold {u_sell} units @ Rs {p_sell} ({reason})", received_amt)
                    st.balloons()
                    st.success(f"Sold {sel_sym}. Profit: {net_pl:.2f}")

# ================= WATCHLIST =================
elif menu == "Watchlist":
    st.title("👀 Watchlist")
    wl = get_data("watchlist.csv")
    
    with st.form("wl_add"):
        c1, c2, c3 = st.columns(3)
        s = c1.text_input("Symbol").upper()
        t = c2.number_input("Target Price")
        n = c3.text_input("Note")
        if st.form_submit_button("Add to Watchlist"):
            new = pd.DataFrame([{"Symbol": s, "Target": t, "Condition": "Below", "Note": n}])
            wl = pd.concat([wl, new], ignore_index=True)
            save_data("watchlist.csv", wl)
            st.success("Added.")

    if not wl.empty:
        st.dataframe(wl, use_container_width=True)
        if st.button("Clear Watchlist"):
            save_data("watchlist.csv", pd.DataFrame(columns=["Symbol", "Target", "Condition", "Note"]))
            st.rerun()

# ================= ACTIVITY LOG =================
elif menu == "Activity Log":
    st.title("🗂 Trade Audit Log")
    st.caption("A chronological record of all actions and system events.")
    
    df = get_data("activity_log.csv")
    
    if df.empty:
        st.info("No activity recorded yet.")
    else:
        with st.expander("🔍 Filter Logs", expanded=False):
            c1, c2 = st.columns(2)
            cats = ["All"] + list(df["Category"].unique())
            sel_cat = c1.selectbox("Category", cats)
            search_sym = c2.text_input("Search Symbol").upper()
        
        filtered_df = df.copy()
        if sel_cat != "All":
            filtered_df = filtered_df[filtered_df["Category"] == sel_cat]
        if search_sym:
            filtered_df = filtered_df[filtered_df["Symbol"].str.contains(search_sym, na=False)]
            
        def highlight_action(val):
            color = 'white'
            if val == 'BUY': color = '#ffcccb'
            elif val == 'SELL': color = '#90ee90'
            return f'background-color: {color}; color: black'

        st.dataframe(
            filtered_df.style.map(highlight_action, subset=['Action'])
            .format({"Amount": "Rs {:,.2f}"}),
            use_container_width=True,
            height=500
        )
        
        st.markdown("### 💰 Cash Flow Summary")
        total_inflow = filtered_df[filtered_df["Amount"] > 0]["Amount"].sum()
        total_outflow = filtered_df[filtered_df["Amount"] < 0]["Amount"].sum()
        net_flow = filtered_df["Amount"].sum()
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Credit (Sales)", f"Rs {total_inflow:,.2f}")
        k2.metric("Total Debit (Buys)", f"Rs {total_outflow:,.2f}")
        k3.metric("Net Cash Flow", f"Rs {net_flow:,.2f}", delta=f"{net_flow:,.2f}")

        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download CSV", csv, "activity_log.csv", "text/csv")

# ================= MANAGE DATA =================
elif menu == "Manage Data":
    st.title("🛠 Data Editor")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Portfolio", "History", "Watchlist", "Activity Log"])
    
    with tab1:
        port = get_data("portfolio.csv")
        edit_port = st.data_editor(port, num_rows="dynamic", use_container_width=True, key="port_edit")
        if st.button("Save Portfolio Changes"):
            if len(edit_port) != len(port) or not edit_port.equals(port):
                log_activity("SYSTEM", "PORTFOLIO", "EDIT", "Manual Edit in Data Editor", 0)
            save_data("portfolio.csv", edit_port)
            st.success("Saved & Logged.")

    with tab2:
        hist = get_data("history.csv")
        edit_hist = st.data_editor(hist, num_rows="dynamic", use_container_width=True, key="hist_edit")
        if st.button("Save History Changes"):
            save_data("history.csv", edit_hist)
            log_activity("SYSTEM", "HISTORY", "EDIT", "Manual Edit in Data Editor", 0)
            st.success("Saved & Logged.")

    with tab3:
        wl = get_data("watchlist.csv")
        edit_wl = st.data_editor(wl, num_rows="dynamic", use_container_width=True, key="wl_edit")
        if st.button("Save Watchlist"):
            save_data("watchlist.csv", edit_wl)
            st.success("Saved.")
            
    with tab4:
        st.warning("⚠️ Editing Logs directly is not recommended.")
        log_df = get_data("activity_log.csv")
        edit_log = st.data_editor(log_df, num_rows="dynamic", use_container_width=True, key="log_edit")
        if st.button("Save Log Changes"):
            save_data("activity_log.csv", edit_log)
            st.success("Logs Saved.")

# ================= DATA ANALYSIS =================
elif menu == "Data Analysis":
    st.title("📈 Performance Charts")
    
    d_log = get_data("data.csv")
    w_log = get_data("wealth_log.csv")
    
    if not d_log.empty:
        st.subheader("Profit/Loss Trend")
        fig = px.line(d_log, x="Date", y=["Realized_PL", "Unrealized_PL", "Total_PL"], markers=True)
        st.plotly_chart(fig, use_container_width=True)
        
    if not w_log.empty:
        st.subheader("Net Worth Growth")
        fig2 = px.area(w_log, x="Date", y="Net_Worth", color_discrete_sequence=["#00CC96"])
        st.plotly_chart(fig2, use_container_width=True)
