import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
from datetime import datetime
import traceback

# --- GITHUB SETUP ---
@st.cache_resource
def get_repo():
    g = Github(st.secrets["github_token"])
    return g.get_user().get_repo(st.secrets["repo_name"])

# --- DATA SCHEMAS (Organized by Folder) ---
SCHEMAS = {
    "nepse/portfolio.csv": ["Symbol", "Total_Qty", "Total_Investment", "WACC"],
    "nepse/history.csv": ["Date", "Symbol", "Type", "Qty", "Price", "Total_Amount", "Broker_Fee", "Capital_Gain_Tax", "Net_Amount", "Remarks"],
    "nepse/watchlist.csv": ["Symbol", "Target_Buy", "Target_Sell", "Notes"],
    "tms/tms_trx.csv": ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"],
    "system/activity_log.csv": ["Date", "Time", "Category", "Symbol", "Action", "Details", "Amount"],
    "system/error_log.csv": ["Date", "Time", "Context", "Error_Message", "Traceback"]
}

def get_data(filepath):
    """Fetches data from GitHub. If it fails or doesn't exist, returns empty DataFrame with correct schema."""
    try:
        repo = get_repo()
        file_content = repo.get_contents(filepath)
        csv_data = file_content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_data))
        return df
    except Exception as e:
        log_error(f"get_data: {filepath}", str(e))
        cols = SCHEMAS.get(filepath, [])
        return pd.DataFrame(columns=cols)

def save_data(filepath, df):
    """Saves data to GitHub. Prevents infinite loops if error logging fails."""
    try:
        repo = get_repo()
        csv_data = df.to_csv(index=False)
        try:
            contents = repo.get_contents(filepath)
            repo.update_file(contents.path, f"Update {filepath}", csv_data, contents.sha)
        except Exception:
            # If the file doesn't exist yet, create it
            repo.create_file(filepath, f"Create {filepath}", csv_data)
            
    except Exception as e:
        # 1. STOP THE INFINITE LOOP
        if filepath != "system/error_log.csv":
            log_error(f"save_data: {filepath}", str(e))
            
        # 2. SHOW THE REAL ERROR ON SCREEN
        st.error(f"🚨 GitHub Blocked Save for {filepath}: {str(e)}")

def log_activity(category, symbol, action, details, amount):
    try:
        df = get_data("system/activity_log.csv")
        now = datetime.now()
        new_entry = pd.DataFrame([{
            "Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"),
            "Category": category, "Symbol": symbol, "Action": action,
            "Details": details, "Amount": amount
        }])
        df = pd.concat([df, new_entry], ignore_index=True)
        save_data("system/activity_log.csv", df)
    except Exception as e:
        log_error("log_activity", str(e))

def log_error(context, error_msg):
    """The new silent error catcher."""
    try:
        df = get_data("system/error_log.csv")
        now = datetime.now()
        new_entry = pd.DataFrame([{
            "Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"),
            "Context": context, "Error_Message": error_msg, "Traceback": traceback.format_exc()
        }])
        df = pd.concat([df, new_entry], ignore_index=True)
        save_data("system/error_log.csv", df)
    except:
        pass # If error logging itself fails, we must pass to avoid infinite loops
