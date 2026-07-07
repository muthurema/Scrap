"""Settings: audio/alert configuration, detection tuning, admin password."""

import os

import streamlit as st

from app import alerts, auth, db
from app.detection.engine import VIOLATION_TYPES


def render():
    st.title("⚙️ Settings")

    # ------------------------------------------------------------- alerts
    st.subheader("🔊 Audio alerts")
    audio_on = st.toggle("Enable spoken audio alerts", value=alerts.audio_enabled())
    cooldown = st.number_input(
        "Alert cooldown (seconds)", 3, 300, alerts.get_cooldown(),
        help="Minimum time between repeated announcements of the same violation "
             "on the same camera.")

    st.markdown("**Announcement phrases** — what is spoken when each violation is detected:")
    phrases = {}
    for vtype, (label, default_phrase) in VIOLATION_TYPES.items():
        phrases[vtype] = st.text_input(label, alerts.get_phrase(vtype), key=f"phrase_{vtype}")

    test_col1, _ = st.columns([1, 3])
    with test_col1:
        if st.button("🔈 Test audio"):
            alerts.speak(["Audio alerts are working"])
            st.caption("You should hear a voice in this browser tab.")

    if st.button("💾 Save alert settings", type="primary"):
        db.set_setting("audio_enabled", "1" if audio_on else "0")
        db.set_setting("alert_cooldown", cooldown)
        for vtype, phrase in phrases.items():
            if phrase.strip():
                db.set_setting(f"phrase_{vtype}", phrase.strip())
        st.success("Alert settings saved.")

    st.divider()

    # ---------------------------------------------------------- detection
    st.subheader("🧠 Detection")
    ppe_path = st.text_input("PPE model weights path",
                             db.get_setting("ppe_model_path", "models/ppe.pt"),
                             help="YOLO model trained on a PPE / construction-safety "
                                  "dataset. See the README for download options.")
    if os.path.exists(ppe_path):
        st.success("PPE model file found ✅")
    else:
        st.warning("File not found — helmet/vest detection will be disabled until "
                   "weights are placed at this path.")
    confidence = st.slider("Minimum detection confidence", 0.1, 0.9,
                           float(db.get_setting("confidence", 0.45)), 0.05)
    if st.button("💾 Save detection settings"):
        db.set_setting("ppe_model_path", ppe_path)
        db.set_setting("confidence", confidence)
        st.session_state.pop("engine", None)  # reload models with new settings
        st.success("Detection settings saved — models will reload on next monitoring start.")

    st.divider()

    # ------------------------------------------------------------ account
    st.subheader("🔑 Admin password")
    if auth.is_default_password():
        st.warning("You are still using the default password (`admin123`). Change it now.")
    with st.form("change_pw"):
        current = st.text_input("Current password", type="password")
        new1 = st.text_input("New password", type="password")
        new2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Change password"):
            if not auth.verify_password(current):
                st.error("Current password is incorrect.")
            elif len(new1) < 8:
                st.error("New password must be at least 8 characters.")
            elif new1 != new2:
                st.error("New passwords do not match.")
            else:
                auth.change_password(new1)
                st.success("Password changed.")
