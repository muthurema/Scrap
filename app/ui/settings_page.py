"""Settings: audio/alert configuration, detection tuning, admin password."""

import os

import streamlit as st

from app import alerts, auth, db
from app.detection import download as model_dl
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
                                  "dataset. Download one below or bring your own.")
    if os.path.exists(ppe_path):
        st.success(f"PPE model file found ✅ ({os.path.getsize(ppe_path) / 1e6:.1f} MB)")
    else:
        st.warning("No PPE model yet — helmet detection is disabled. Download one below "
                   "(needs internet) or place your own weights at this path.")
        choice = st.selectbox(
            "Model to download", list(model_dl.PPE_MODEL_CHOICES),
            format_func=lambda k: model_dl.PPE_MODEL_CHOICES[k]["label"])
        if st.button("⬇️ Download PPE model", type="primary"):
            bar = st.progress(0.0, "Downloading model weights ...")
            ok, msg = model_dl.download_ppe_model(
                choice, ppe_path, progress_cb=lambda f: bar.progress(f))
            bar.empty()
            if ok:
                st.session_state.pop("engine", None)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    if not os.path.exists("yolov8n-pose.pt"):
        st.caption("The pose model for handrail detection (`yolov8n-pose.pt`) is fetched "
                   "automatically by ultralytics on first monitoring start.")
        if st.button("⬇️ Download pose model now"):
            bar = st.progress(0.0, "Downloading pose model ...")
            ok, msg = model_dl.download_pose_model(progress_cb=lambda f: bar.progress(f))
            bar.empty()
            if ok:
                st.session_state.pop("engine", None)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
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
