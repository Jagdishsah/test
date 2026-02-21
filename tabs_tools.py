import streamlit as st
import pandas as pd
from datetime import datetime
from core_db import get_data, save_data
from core_logic import calculate_trade_metrics, get_broker_commission, DP_CHARGE, SEBON_FEE

def render():
    st.title("🛠️ Tools & Analysis")
    tabs = st.tabs(["🔮 What If Simulator", "📉 WACC Projection", "📖 Trading Journal"])
    
    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        price = c1.number_input("Buy Price", 100.0)
        qty = c2.number_input("Quantity", 10)
        target = c3.number_input("Target Price", 0.0)
        stop_loss = c4.number_input("Stop Loss", 0.0)
        if st.button("Simulate Trade"):
            raw = price * qty
            total_cost = raw + get_broker_commission(raw) + DP_CHARGE + (raw * SEBON_FEE)
            st.write(f"Total Invested: **Rs {total_cost:,.2f}** | Break-Even: **Rs {total_cost/qty:.2f}**")
            if target > 0:
                _, pl, _, _ = calculate_trade_metrics(qty, total_cost, target)
                st.success(f"Target Profit: Rs {pl:,.0f}")

    with tabs[1]:
        st.write("Calculate Average Cost.")
        c1, c2, c3, c4 = st.columns(4)
        o_qty = c1.number_input("Old Qty", 10)
        o_wacc = c2.number_input("Old WACC", 200.0)
        n_qty = c3.number_input("New Qty", 10)
        n_price = c4.number_input("New Price", 150.0)
        if st.button("Calculate Final WACC"):
            n_raw = n_price * n_qty
            n_cost = n_raw + get_broker_commission(n_raw) + DP_CHARGE + (n_raw * SEBON_FEE)
            final_wacc = ((o_qty * o_wacc) + n_cost) / (o_qty + n_qty)
            st.info(f"New WACC will be: Rs {final_wacc:.2f}")

    with tabs[2]:
        diary = get_data("nepse/diary.csv")
        with st.form("diary"):
            sym = st.text_input("Symbol")
            note = st.text_area("Trade Note")
            emo = st.selectbox("Emotion", ["Neutral 😐", "Fear 😨", "Greed 🤑", "Calm 🧘"])
            if st.form_submit_button("Save Entry"):
                new_entry = pd.DataFrame([{"Date": datetime.now().strftime("%Y-%m-%d"), "Symbol": sym, "Note": note, "Emotion": emo, "Mistake": "", "Strategy": ""}])
                save_data("nepse/diary.csv", pd.concat([diary, new_entry], ignore_index=True))
                st.success("Journal Updated!")
        st.dataframe(diary, hide_index=True)
