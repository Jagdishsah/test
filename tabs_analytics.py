import streamlit as st
import pandas as pd
import plotly.express as px
from core_db import get_data
from core_logic import calculate_tms_metrics

def render():
    st.title("📈 Advanced Analytics")
    tabs = st.tabs(["📉 Trade Replay", "🛡️ Cash Utilization", "🔥 System Errors"])
    
    # --- FEATURE: TRADE REPLAY ---
    with tabs[0]:
        st.subheader("Trade Replay Engine")
        st.caption("Visual timeline of your moves on a specific stock.")
        hist = get_data("nepse/history.csv")
        if not hist.empty:
            symbols = hist["Symbol"].unique()
            target = st.selectbox("Select Stock to Replay", symbols)
            
            target_df = hist[hist["Symbol"] == target].copy()
            target_df["Date"] = pd.to_datetime(target_df["Date"])
            target_df = target_df.sort_values("Date")
            
            fig = px.scatter(target_df, x="Date", y="Price", color="Type", size="Qty", 
                             title=f"Trade Replay: {target}", color_discrete_map={"BUY":"red", "SELL":"green"})
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(target_df[["Date", "Type", "Qty", "Price"]], hide_index=True)

    # --- FEATURE: CASH UTILIZATION % ---
    with tabs[1]:
        st.subheader("Capital Efficiency")
        port = get_data("nepse/portfolio.csv")
        trx = get_data("tms/tms_trx.csv")
        
        invested_value = port["Total_Investment"].sum() if not port.empty else 0
        _, buying_power, _, _ = calculate_tms_metrics(trx)
        
        total_capital = invested_value + buying_power
        if total_capital > 0:
            utilization = (invested_value / total_capital) * 100
            st.metric("Cash Utilization %", f"{utilization:.1f}%", help="What % of your total available money is actually invested?")
            st.progress(utilization / 100)
        else:
            st.info("Load data to calculate utilization.")
            
    # --- ADMIN: ERROR LOGS ---
    with tabs[2]:
        st.subheader("Silent System Errors")
        err = get_data("system/error_log.csv")
        if not err.empty:
            st.error(f"System has suppressed {len(err)} background errors.")
            st.dataframe(err.sort_values("Date", ascending=False), hide_index=True)
        else:
            st.success("No background errors detected!")
