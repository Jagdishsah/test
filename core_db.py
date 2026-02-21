import streamlit as st
import pandas as pd
from github import Github, GithubException
from io import StringIO
from datetime import datetime
import traceback

# --- GITHUB SETUP ---
@st.cache_resource
def get_repo():
    g = Github(st.secrets["github_token"])
    return g.get_repo("Jagdishsah/test")

# --- DATA SCHEMAS ---
SCHEMAS = {
    "nepse/portfolio.csv": ["Symbol", "Total_Qty", "Total_Investment", "WACC", "Sector", "Buy_Date", "Stop_Loss", "Notes"],
    "nepse/history.csv": ["Date", "Symbol", "Type", "Qty", "Price", "Total_Amount", "Broker_Fee", "Capital_Gain_Tax", "Net_Amount", "Remarks"],
    "nepse/watchlist.csv": ["Symbol", "Target", "Remark"],
    "nepse/diary.csv": ["Date", "Symbol", "Note", "Emotion", "Mistake", "Strategy"],
    "tms/tms_trx.csv": ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"],
    "system/activity_log.csv": ["Date", "Time", "Category", "Symbol", "Action", "Details", "Amount"],
    "system/error_log.csv": ["Date", "Time", "Context", "Error_Message", "Traceback"],
    "system/cache.csv": ["Symbol", "LTP", "Change", "High52", "Low52", "LastUpdated"],
    "system/wealth.csv": ["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"],
    "system/Data.csv": ["Date", "Realized_PL", "Realized_PL_Pct", "Unrealized_PL", "Unrealized_PL_Pct"]
}

def github_save(filepath, content_str, message):
    repo = get_repo()
    try:
        contents = repo.get_contents(filepath)
        repo.update_file(contents.path, f"Update {message}", content_str, contents.sha)
    except GithubException as e:
        if e.status == 404:
            repo.create_file(filepath, f"Create {message}", content_str)
        else: raise e

def get_data(filepath):
    try:
        repo = get_repo()
        file_content = repo.get_contents(filepath)
        return pd.read_csv(StringIO(file_content.decoded_content.decode('utf-8')))
    except Exception as e:
        if filepath != "system/error_log.csv": log_error(f"get_data: {filepath}", str(e))
        return pd.DataFrame(columns=SCHEMAS.get(filepath, []))

def save_data(filepath, df):
    try:
        github_save(filepath, df.to_csv(index=False), filepath)
    except Exception as e:
        if filepath != "system/error_log.csv": log_error(f"save_data: {filepath}", str(e))
        st.error(f"🚨 GitHub Blocked Save for {filepath}: {str(e)}")

def log_activity(category, symbol, action, details, amount):
    try:
        df = get_data("system/activity_log.csv")
        now = datetime.now()
        new_entry = pd.DataFrame([{"Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"), "Category": category, "Symbol": symbol, "Action": action, "Details": details, "Amount": amount}])
        save_data("system/activity_log.csv", pd.concat([df, new_entry], ignore_index=True))
    except Exception as e: log_error("log_activity", str(e))

def log_error(context, error_msg):
    try:
        df = get_data("system/error_log.csv")
        now = datetime.now()
        new_entry = pd.DataFrame([{"Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"), "Context": context, "Error_Message": error_msg, "Traceback": traceback.format_exc()}])
        github_save("system/error_log.csv", pd.concat([df, new_entry], ignore_index=True).to_csv(index=False), "Error Log")
    except: pass
