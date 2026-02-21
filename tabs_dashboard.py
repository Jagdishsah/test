import streamlit as st
import pandas as pd
import plotly.express as px
from core_db import get_data
from core_logic import refresh_market_cache

def render():
    st.title("📊 Market Dashboard")
    
    port = get_data("nepse/portfolio.csv")
    cache = get_data("system/cache.csv")
    hist = get_data("nepse/history.csv")
    
    df = pd.merge(port, cache, on="Symbol", how="left").fillna(0) if not port.empty and not cache.empty else port.copy()
    if not df.empty and "LTP" not in df.columns: df["LTP"] = 0
    
    curr_inv = df["Total_Investment"].sum() if not df.empty else 0
    curr_val, day_change = 0, 0
    sector_data, alerts = {}, []
    
    for _, row in df.iterrows():
        ltp = row.get("LTP", 0) or row.get("WACC", 0)
        val = row["Total_Qty"] * ltp
        d_chg = row["Total_Qty"] * row.get("Change", 0)
        curr_val += val
        day_change += d_chg
        
        sec = row.get("Sector", "Unclassified")
        sector_data[sec] = sector_data.get(sec, 0) + val
        
        sl = row.get("Stop_Loss", 0)
        if sl > 0 and ltp < sl: alerts.append(f"⚠️ **STOP LOSS HIT:** {row['Symbol']} @ Rs {ltp}")

    curr_pl = curr_val - curr_inv
    curr_ret = (curr_pl / curr_inv * 100) if curr_inv else 0

    realized_pl, realized_inv, realized_recv = 0, 0, 0
    if not hist.empty:
        sells = hist[hist["Type"] == "SELL"]
        buys = hist[hist["Type"] == "BUY"]
        realized_pl = sells["Net_Amount"].sum() - (sells["Qty"] * sells["Price"]).sum() # Approximation for old migrated data
        realized_inv = buys["Total_Amount"].sum()
        realized_recv = sells["Net_Amount"].sum()

    st.markdown("### 🏦 Net Worth Snapshot")
    m1, m2, m3 = st.columns(3)
    m1.metric("Current Portfolio Value", f"Rs {curr_val:,.0f}")
    m2.metric("Total Active Investment", f"Rs {curr_inv:,.0f}")
    m3.metric("Today's Change", f"Rs {day_change:,.0f}", delta=day_change)
    
    st.markdown("### ⚖️ Profit/Loss Analysis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Net Realized P/L", f"Rs {realized_pl:,.0f}")
    c2.metric("📈 Unrealized P/L", f"Rs {curr_pl:,.0f}", delta=f"{curr_ret:.2f}%")
    c3.metric("🏆 Lifetime P/L", f"Rs {realized_pl + curr_pl:,.0f}")
    c4.metric("🥇 Capital Turnover", f"{(realized_inv / curr_inv * 100) if curr_inv else 0:.1f}%")

    col_chart, col_alert = st.columns([2, 1])
    with col_chart:
        st.subheader("Sector Allocation")
        if sector_data:
            fig = px.pie(names=list(sector_data.keys()), values=list(sector_data.values()), hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    
    with col_alert:
        st.subheader("📢 Alerts")
        for a in alerts: st.error(a)
        wl = get_data("nepse/watchlist.csv")
        if not wl.empty and not cache.empty:
            wl_m = pd.merge(wl, cache, on="Symbol", how="left")
            for _, h in wl_m[(wl_m["LTP"] <= wl_m["Target"]) & (wl_m["LTP"] > 0)].iterrows():
                st.success(f"🎯 **BUY TARGET:** {h['Symbol']} @ {h['LTP']}")
