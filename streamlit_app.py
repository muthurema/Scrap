"""SafetyWatch — CCTV safety-violation monitoring with instant voice alerts.

Run with:  streamlit run streamlit_app.py
Default admin password: admin123 (change it in Settings after first login).
"""

import streamlit as st

from app import auth, db

st.set_page_config(page_title="SafetyWatch", page_icon="🦺", layout="wide")

db.init_db()
auth.ensure_default_admin()


def _login_screen():
    st.title("🦺 SafetyWatch")
    st.caption("CCTV safety monitoring — PPE compliance, handrail use, instant voice alerts.")
    with st.form("login"):
        password = st.text_input("Admin password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if auth.verify_password(password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Wrong password.")
    if auth.is_default_password():
        st.info("First run? The default admin password is `admin123` — "
                "change it in **Settings** after signing in.")


if not st.session_state.get("authenticated"):
    _login_screen()
    st.stop()

from app.ui import cameras_page, dashboard_page, monitor_page, settings_page, violations_page

pages = st.navigation([
    st.Page(dashboard_page.render, title="Dashboard", icon="🦺",
            url_path="dashboard", default=True),
    st.Page(cameras_page.render, title="Camera administration", icon="🎥",
            url_path="cameras"),
    st.Page(monitor_page.render, title="Live monitoring", icon="🔴",
            url_path="monitor"),
    st.Page(violations_page.render, title="Violation history", icon="📋",
            url_path="violations"),
    st.Page(settings_page.render, title="Settings", icon="⚙️",
            url_path="settings"),
])

with st.sidebar:
    st.markdown("---")
    if st.button("🚪 Sign out"):
        st.session_state.clear()
        st.rerun()

pages.run()
