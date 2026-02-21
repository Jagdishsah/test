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

# --- THE MISSING TRADE ENGINE ---
def execute_trade_logic(trade_type, symbol, qty, price, remarks=""):
    port = get_data("nepse/portfolio.csv")
    hist = get_data("nepse/history.csv")
    
    raw_amt = qty * price
    broker_fee = get_broker_commission(raw_amt)
    sebon = raw_amt * SEBON_FEE
    
    symbol = symbol.upper().strip()
    now_date = datetime.now().strftime("%Y-%m-%d")
    
    if trade_type == "BUY":
        total_cost = raw_amt + broker_fee + sebon + DP_CHARGE
        cgt = 0
        net_amt = total_cost
        
        if symbol in port['Symbol'].values:
            idx = port.index[port['Symbol'] == symbol].tolist()[0]
            old_qty = port.at[idx, 'Total_Qty']
            old_inv = port.at[idx, 'Total_Investment']
            new_qty = old_qty + qty
            new_inv = old_inv + total_cost
            port.at[idx, 'Total_Qty'] = new_qty
            port.at[idx, 'Total_Investment'] = new_inv
            port.at[idx, 'WACC'] = new_inv / new_qty
        else:
            new_row = pd.DataFrame([{
                "Symbol": symbol, "Total_Qty": qty, 
                "Total_Investment": total_cost, "WACC": total_cost / qty,
                "Sector": "Unclassified", "Buy_Date": now_date,
                "Stop_Loss": 0.0, "Notes": ""
            }])
            port = pd.concat([port, new_row], ignore_index=True)
            
    elif trade_type == "SELL":
        gross_recv = raw_amt - broker_fee - sebon - DP_CHARGE
        cgt = 0
        net_amt = gross_recv
        
        if symbol in port['Symbol'].values:
            idx = port.index[port['Symbol'] == symbol].tolist()[0]
            wacc = port.at[idx, 'WACC']
            cost_basis = wacc * qty
            profit = gross_recv - cost_basis
            
            if profit > 0:
                cgt = profit * CGT_SHORT  # Defaulting to 7.5% for automation
                net_amt = gross_recv - cgt
            
            old_qty = port.at[idx, 'Total_Qty']
            if qty >= old_qty:
                port = port.drop(idx)
            else:
                new_qty = old_qty - qty
                port.at[idx, 'Total_Qty'] = new_qty
                port.at[idx, 'Total_Investment'] = new_qty * wacc
                
    # Update History
    new_hist = pd.DataFrame([{
        "Date": now_date, "Symbol": symbol, "Type": trade_type, 
        "Qty": qty, "Price": price, "Total_Amount": raw_amt, 
        "Broker_Fee": broker_fee, "Capital_Gain_Tax": cgt, 
        "Net_Amount": net_amt, "Remarks": remarks
    }])
    hist = pd.concat([hist, new_hist], ignore_index=True)
    
    # Save & Log
    save_data("nepse/portfolio.csv", port)
    save_data("nepse/history.csv", hist)
    
    log_amt = -net_amt if trade_type == "BUY" else net_amt
    log_activity("TRADE", symbol, trade_type, remarks, log_amt)

def refresh_market_cache():
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
