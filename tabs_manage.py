import streamlit as st
from core_db import get_data, save_data

def render():
    st.title("🗂 Data Manager & Logs")
    tabs = st.tabs(["Activity Logs", "Edit Portfolios", "Edit History", "Edit Watchlist"])
    
    with tabs[0]:
        st.dataframe(get_data("system/activity_log.csv").sort_values("Date", ascending=False), use_container_width=True)
    with tabs[1]:
        df = get_data("nepse/portfolio.csv")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Save Portfolio"): save_data("nepse/portfolio.csv", edited)
    with tabs[2]:
        df = get_data("nepse/history.csv")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Save History"): save_data("nepse/history.csv", edited)
    with tabs[3]:
        df = get_data("nepse/watchlist.csv")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Save Watchlist"): save_data("nepse/watchlist.csv", edited)
