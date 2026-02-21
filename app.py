import streamlit as st
import tabs_portfolio
import tabs_tms
import tabs_analytics

st.set_page_config(page_title="NEPSE Pro OS", page_icon="📈", layout="wide")

# --- AUTHENTICATION ---
if "login_correct" not in st.session_state:
    st.session_state["login_correct"] = False

if not st.session_state["login_correct"]:
    st.header("🔒 NEPSE Pro OS")
    with st.form("credentials_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Log In", type="primary"):
            if u == st.secrets["app_username"] and p == st.secrets["app_password"]:
                st.session_state["login_correct"] = True
                st.rerun()
            else:
                st.error("Invalid credentials.")
else:
    # --- MAIN ROUTER ---
    st.sidebar.title("🚀 Navigation")
    menu = st.sidebar.radio("Modules", ["My Portfolio", "My TMS", "Analytics Engine"])
    
    if st.sidebar.button("Logout"):
        st.session_state["login_correct"] = False
        st.rerun()

    # Route to the specific file based on selection
    if menu == "My Portfolio":
        tabs_portfolio.render()
    elif menu == "My TMS":
        tabs_tms.render()
    elif menu == "Analytics Engine":
        tabs_analytics.render()
