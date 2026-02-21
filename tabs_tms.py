import streamlit as st
import pandas as pd
from datetime import datetime
from core_db import get_data, save_data, log_activity
from core_logic import calculate_tms_metrics

def render():
    st.title("🏦 TMS Command Center")
    tms_tabs = st.tabs(["📊 Dashboard", "✍️ Add Transaction", "📜 Ledger"])
    
    # --- DASHBOARD ---
    with tms_tabs[0]:
        trx_df = get_data("tms/tms_trx.csv")
        
        net_balance, buying_power, cash_in, cash_out = calculate_tms_metrics(trx_df)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Net Balance", f"Rs {net_balance:,.2f}")
        c2.metric("🔋 Buying Power", f"Rs {buying_power:,.2f}")
        c3.metric("Real Cash In", f"Rs {cash_in:,.2f}")
        c4.metric("Real Cash Out", f"Rs {cash_out:,.2f}")
        
    # --- ADD TRANSACTION ---
    with tms_tabs[1]:
        with st.form("tms_form"):
            date = st.date_input("Date")
            type_sel = st.selectbox("Type", ["Deposit", "Withdraw", "Buy", "Sell", "Collateral Load", "Fine", "Other"])
            medium = st.selectbox("Medium", ["Global", "Esewa", "CIPS", "Collateral", "Other"])
            amount = st.number_input("Amount", min_value=0.0)
            charge = st.number_input("Charge", min_value=0.0)
            
            if st.form_submit_button("Save to Ledger"):
                # Auto-sign logic
                final_amt = -amount if type_sel in ["Buy", "Withdraw", "Fine"] else amount
                
                new_trx = pd.DataFrame([{"Date": date, "Stock": "", "Type": type_sel, "Medium": medium, "Amount": final_amt, "Charge": charge, "Remark": "", "Reference": ""}])
                trx_df = get_data("tms/tms_trx.csv")
                trx_df = pd.concat([trx_df, new_trx], ignore_index=True)
                save_data("tms/tms_trx.csv", trx_df)
                
                log_activity("TMS", "N/A", "ADD", f"{type_sel} via {medium}", final_amt)
                st.success("✅ Saved to TMS Ledger.")

    with tms_tabs[2]:
        st.dataframe(get_data("tms/tms_trx.csv"), hide_index=True)
