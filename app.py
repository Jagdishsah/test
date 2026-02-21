import streamlit as st
from core_logic import refresh_market_cache
import tabs_dashboard
import tabs_portfolio
import tabs_tms
import tabs_tools
import tabs_manage
import tabs_analytics

st.set_page_config(page_title="NEPSE Pro OS", page_icon="📈", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {background-color: #0E1117; border: 1px solid #262730; padding: 15px; border-radius: 5px; margin-bottom: 10px;}
    .success-text {color: #00FF00;}
    .danger-text {color: #FF4B4B;}
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION ---
if "login_correct" not in st.session_state: st.session_state["login_correct"] = False

if not st.session_state["login_correct"]:
    st.header("🔒 NEPSE Pro OS")
    with st.form("credentials_form"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Log In", type="primary"):
            if u == st.secrets["app_username"] and p == st.secrets["app_password"]:
                st.session_state["login_correct"] = True
                st.rerun()
            else: st.error("Invalid credentials.")
else:
    # --- NAVIGATION ---
    st.sidebar.title("🚀 Navigation")
    menu = st.sidebar.radio("Modules", ["Dashboard", "Portfolio & Trade", "TMS Command", "Tools & Simulators", "Analytics Engine", "Manage Data"])
    
    if st.sidebar.button("🔄 Refresh Market Data"):
        refresh_market_cache()
        st.rerun()
        
    if st.sidebar.button("Logout"):
        st.session_state["login_correct"] = False
        st.rerun()

    if menu == "Dashboard": tabs_dashboard.render()
    elif menu == "Portfolio & Trade": tabs_portfolio.render()
    elif menu == "TMS Command": tabs_tms.render()
    elif menu == "Tools & Simulators": tabs_tools.render()
    elif menu == "Analytics Engine": tabs_analytics.render()
    elif menu == "Manage Data": tabs_manage.render()
