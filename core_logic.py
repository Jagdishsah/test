import pandas as pd
import streamlit as st
from decimal import Decimal, getcontext
from datetime import datetime
from core_db import get_data, save_data, log_activity
from scrape import get_market_data

getcontext().prec = 10 

# --- BROKER & TAX CONSTANTS ---
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

def get_broker_commission(amount):
    if amount <= 50000: rate = 0.36
    elif amount <= 500000: rate = 0.33
    elif amount <= 2000000: rate = 0.31
    else: rate = 0.27
    return max(10, amount * rate / 100)

def calculate_trade_metrics(units, cost, ltp, change=0):
    if units == 0: return 0, 0, 0, 0
    curr_val = units * ltp
    day_gain = units * change
    overhead = cost * 0.006 + 25
    be_price = (cost + overhead) / units
    sell_comm = get_broker_commission(curr_val)
    sebon = curr_val * SEBON_FEE
    receivable = curr_val - sell_comm - sebon - DP_CHARGE
    net_pl = receivable - cost
    if net_pl > 0: net_pl -= (net_pl * CGT_SHORT)
    return curr_val, net_pl, be_price, day_gain

def refresh_market_cache():
    """Fetches live API data and updates cache silently."""
    port = get_data("nepse/portfolio.csv")
    watch = get_data("nepse/watchlist.csv")
    symbols = set(port["Symbol"].tolist() + (watch["Symbol"].tolist() if not watch.empty else []))
    
    if not symbols: return
    progress = st.progress(0, "Connecting to High-Speed API...")
    now_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M")
    
    market_data = get_market_data(list(symbols))
    cache_list = []
    
    for i, sym in enumerate(symbols):
        progress.progress((i+1)/len(symbols), f"Processing {sym}...")
        live = market_data.get(sym, {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0})
        cache_list.append({
            "Symbol": sym, "LTP": live['price'], "Change": live['change'], 
            "High52": live['high'], "Low52": live['low'], "LastUpdated": now_str
        })
        
    progress.empty()
    save_data("system/cache.csv", pd.DataFrame(cache_list))
    st.toast("⚡ Market Data synced via API!", icon="✅")

def calculate_tms_metrics(trx_df):
    if trx_df.empty: return Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')
    trx_df['Amount_Dec'] = trx_df['Amount'].apply(lambda x: Decimal(str(x)))
    trx_df['Charge_Dec'] = trx_df['Charge'].apply(lambda x: Decimal(str(x)))
    is_collat = (trx_df["Medium"].str.upper() == "COLLATERAL") | (trx_df["Type"].str.upper() == "COLLATERAL LOAD")
    real_cash = trx_df[~is_collat]
    cash_in = real_cash[real_cash["Amount_Dec"] > Decimal('0')]["Amount_Dec"].sum()
    cash_out = abs(real_cash[real_cash["Amount_Dec"] < Decimal('0')]["Amount_Dec"].sum())
    total_charges = trx_df["Charge_Dec"].sum()
    net_balance = (cash_in - cash_out) - total_charges
    base_collat = Decimal('10824')
    loaded_collat = trx_df[trx_df["Type"].str.upper() == "COLLATERAL LOAD"]["Amount_Dec"].sum()
    buying_power = ((base_collat + loaded_collat) * Decimal('4')) + net_balance
    return float(net_balance), float(buying_power), float(cash_in), float(cash_out)
