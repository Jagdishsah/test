import streamlit as st
import pandas as pd
from github import Github, GithubException
from io import StringIO
from datetime import datetime
import traceback

# --- GITHUB SETUP ---
@st.cache_resource
def get_repo():
    # Token stays in secrets, repo is hardcoded as requested
    g = Github(st.secrets["github_token"])
    return g.get_repo("Jagdishsah/test")

# --- DATA SCHEMAS (Organized by Folder) ---
SCHEMAS = {
    "nepse/portfolio.csv": ["Symbol", "Total_Qty", "Total_Investment", "WACC"],
    "nepse/history.csv": ["Date", "Symbol", "Type", "Qty", "Price", "Total_Amount", "Broker_Fee", "Capital_Gain_Tax", "Net_Amount", "Remarks"],
    "nepse/watchlist.csv": ["Symbol", "Target_Buy", "Target_Sell", "Notes"],
    "tms/tms_trx.csv": ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"],
    "system/activity_log.csv": ["Date", "Time", "Category", "Symbol", "Action", "Details", "Amount"],
    "system/error_log.csv": ["Date", "Time", "Context", "Error_Message", "Traceback"]
}

def github_save(filepath, content_str, message):
    """Bulletproof GitHub save helper that properly handles SHA codes."""
    repo = get_repo()
    try:
        # Step 1: Try to get the existing file
        contents = repo.get_contents(filepath)
        # If it exists, UPDATE it using its specific SHA
        repo.update_file(contents.path, f"Update {message}", content_str, contents.sha)
    except GithubException as e:
        # Step 2: If the file TRULY doesn't exist (404), then CREATE it
        if e.status == 404:
            repo.create_file(filepath, f"Create {message}", content_str)
        else:
            # If it's a different API error (like 422), raise it so we know
            raise e

def get_data(filepath):
    try:
        repo = get_repo()
        file_content = repo.get_contents(filepath)
        csv_data = file_content.decoded_content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_data))
        return df
    except Exception as e:
        # Prevent infinite loops by not logging if the error log itself fails
        if filepath != "system/error_log.csv":
            log_error(f"get_data: {filepath}", str(e))
        
        # Return empty schema if file doesn't exist yet
        cols = SCHEMAS.get(filepath, [])
        return pd.DataFrame(columns=cols)

def save_data(filepath, df):
    try:
        csv_data = df.to_csv(index=False)
        github_save(filepath, csv_data, filepath)
    except Exception as e:
        if filepath != "system/error_log.csv":
            log_error(f"save_data: {filepath}", str(e))
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
    try:
        df = get_data("system/error_log.csv")
        now = datetime.now()
        new_entry = pd.DataFrame([{
            "Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"),
            "Context": context, "Error_Message": error_msg, "Traceback": traceback.format_exc()
        }])
        df = pd.concat([df, new_entry], ignore_index=True)
        csv_data = df.to_csv(index=False)
        github_save("system/error_log.csv", csv_data, "Error Log")
    except Exception as e:
        st.sidebar.error(f"Critical Logging Failure: {str(e)}")
