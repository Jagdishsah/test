import streamlit as st
import pandas as pd
from datetime import datetime
from core_db import get_data, save_data, log_activity
from core_logic import execute_trade_logic
from scrape import get_market_data

def render():
    st.title("💼 NEPSE Portfolio & Trading")
    
    tabs = st.tabs(["📊 Holdings", "➕ Execute Trade", "📜 Trade History"])
    
    # --- TAB 1: HOLDINGS ---
    with tabs[0]:
        port_df = get_data("nepse/portfolio.csv")
        if not port_df.empty:
            st.dataframe(port_df, use_container_width=True, hide_index=True)
        else:
            st.info("Portfolio is empty.")

    # --- TAB 2: EXECUTE TRADE ---
    with tabs[1]:
        st.subheader("Execute a Buy or Sell")
        with st.form("trade_form"):
            col1, col2, col3 = st.columns(3)
            date = col1.date_input("Date")
            symbol = col2.text_input("Symbol").upper().strip()
            trade_type = col3.selectbox("Type", ["BUY", "SELL"])
            
            qty = st.number_input("Quantity", min_value=1, value=10)
            price = st.number_input("Price", value=0.0)
            
            submitted = st.form_submit_button("Submit Trade")
            
            if submitted and symbol:
                # 1. Validation & Discipline Override Check
                port_df = get_data("nepse/portfolio.csv")
                current_holding = port_df[port_df["Symbol"] == symbol]["Total_Qty"].sum() if not port_df.empty else 0
                
                warning = execute_trade_logic(trade_type, qty, price, current_holding)
                if warning:
                    st.warning(f"⚠️ {warning} Proceeding anyway...")
                
                # 2. Record to History
                hist_df = get_data("nepse/history.csv")
                total_amt = qty * price
                new_hist = pd.DataFrame([{"Date": date, "Symbol": symbol, "Type": trade_type, "Qty": qty, "Price": price, "Total_Amount": total_amt, "Broker_Fee": 0, "Capital_Gain_Tax": 0, "Net_Amount": total_amt, "Remarks": "Manual"}])
                hist_df = pd.concat([hist_df, new_hist], ignore_index=True)
                save_data("nepse/history.csv", hist_df)
                
                # 3. Update Portfolio (Simplified for snippet)
                log_activity("NEPSE", symbol, trade_type, f"{trade_type} {qty} units", total_amt)
                st.success(f"✅ {trade_type} executed for {symbol}.")

    # --- TAB 3: HISTORY ---
    with tabs[2]:
        hist_df = get_data("nepse/history.csv")
        if not hist_df.empty:
            st.dataframe(hist_df.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
