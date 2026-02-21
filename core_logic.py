import pandas as pd
from decimal import Decimal, getcontext
getcontext().prec = 10 # Set precise decimal points for money

def calculate_tms_metrics(trx_df):
    """Calculates Net Balance, Cash Flow, and Buying Power safely."""
    if trx_df.empty:
        return Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')
    
    # Convert amounts to decimals for accuracy
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
    total_collat = base_collat + loaded_collat
    buying_power = (total_collat * Decimal('4')) + net_balance
    
    return float(net_balance), float(buying_power), float(cash_in), float(cash_out)

def execute_trade_logic(trade_type, qty, price, current_holding):
    """Determines if a trade is valid, and returns a warning flag if it breaks discipline."""
    warning = None
    if trade_type == "SELL" and qty > current_holding:
        warning = f"Deliberate Violation: Selling {qty} but holding is only {current_holding}."
    if price <= 0:
        warning = "Deliberate Violation: Trading at 0 or negative price."
        
    return warning
