"""Live monitoring: runs detection on all selected cameras, shows annotated
feeds and fires immediate audio alerts when violations are found."""

import os
import time
from datetime import datetime

import cv2
import streamlit as st

from app import alerts, db
from app.camera import CameraStream
from app.detection.engine import DetectionEngine


def _get_engine():
    if "engine" not in st.session_state:
        st.session_state.engine = DetectionEngine(
            ppe_model_path=db.get_setting("ppe_model_path", "models/ppe.pt"),
            confidence=float(db.get_setting("confidence", 0.45)),
        )
    return st.session_state.engine


def _save_snapshot(frame, camera_name, vtype):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = "".join(c if c.isalnum() else "_" for c in camera_name)[:40]
    path = os.path.join(db.SNAPSHOT_DIR, f"{ts}_{safe_name}_{vtype}.jpg")
    cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return path


def _stop_streams():
    for stream in st.session_state.get("streams", {}).values():
        stream.stop()
    st.session_state.streams = {}


def render():
    st.title("🔴 Live monitoring")

    engine = _get_engine()
    cameras = db.list_cameras(enabled_only=True)
    if not cameras:
        st.info("No enabled cameras. Add and enable cameras in **Camera administration** first.")
        return

    # Surface model availability so the operator knows what's active.
    engine._load_models()
    caps = []
    caps.append("🪖 PPE detection: " + ("**active**" if engine.ppe_available else "unavailable"))
    caps.append("🤚 Handrail detection: " + ("**active**" if engine.pose_available else "unavailable"))
    st.markdown(" · ".join(caps))
    for note in engine.status_notes:
        st.warning(note)
    if not engine.ppe_available or not engine.pose_available:
        if st.button("⬇️ Download missing detection models now"):
            from app.detection import download as model_dl
            with st.spinner("Downloading model weights ..."):
                results = model_dl.ensure_models(
                    db.get_setting("ppe_model_path", "models/ppe.pt"))
            for label, ok, msg in results:
                (st.success if ok else st.error)(f"{label}: {msg}")
            if all(ok for _, ok, _ in results):
                st.session_state.pop("engine", None)
                st.rerun()

    names = {c["id"]: f"{c['name']}{' (' + c['location'] + ')' if c['location'] else ''}"
             for c in cameras}
    col_sel, col_int = st.columns([3, 1])
    with col_sel:
        selected_ids = st.multiselect("Cameras to monitor", list(names),
                                      default=list(names), format_func=names.get)
    with col_int:
        interval = st.number_input("Analysis interval (s)", 0.5, 10.0, 1.0, 0.5,
                                   help="How often each camera frame is analyzed.")

    monitoring = st.session_state.get("monitoring", False)
    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("▶ Start", type="primary", disabled=monitoring or not selected_ids):
            st.session_state.monitoring = True
            st.rerun()
    with c2:
        if st.button("⏹ Stop", disabled=not monitoring):
            st.session_state.monitoring = False
            _stop_streams()
            st.rerun()

    if not st.session_state.get("monitoring"):
        _stop_streams()
        st.caption("Press **Start** to begin monitoring. Audio alerts play in this browser tab — "
                   "keep it open and unmuted at the operator station.")
        return

    selected = [c for c in cameras if c["id"] in selected_ids]

    # Start/reuse background readers for the selected cameras.
    streams = st.session_state.setdefault("streams", {})
    for cam in selected:
        if cam["id"] not in streams:
            streams[cam["id"]] = CameraStream(cam).start()
    for cam_id in [k for k in streams if k not in selected_ids]:
        streams.pop(cam_id).stop()

    alert_mgr = st.session_state.setdefault("alert_mgr", alerts.AlertManager())
    alert_mgr.cooldown = alerts.get_cooldown()
    audio_on = alerts.audio_enabled()

    st.success(f"Monitoring **{len(selected)}** camera(s) — alerts every "
               f"{alert_mgr.cooldown}s max per camera & violation type. "
               f"Audio {'on 🔊' if audio_on else 'off 🔇'}")

    # Layout: grid of camera tiles + a live event feed + a hidden audio slot.
    cols_per_row = 2 if len(selected) > 1 else 1
    placeholders = {}
    rows = [selected[i:i + cols_per_row] for i in range(0, len(selected), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, cam in zip(cols, row):
            with col:
                st.markdown(f"**{cam['name']}**" + (f" · {cam['location']}" if cam['location'] else ""))
                placeholders[cam["id"]] = (st.empty(), st.empty())  # image, status line
    audio_slot = st.empty()
    st.markdown("**Latest events**")
    event_slot = st.empty()
    events = st.session_state.setdefault("live_events", [])

    while st.session_state.get("monitoring"):
        cycle_phrases = []
        for cam in selected:
            stream = streams[cam["id"]]
            img_ph, status_ph = placeholders[cam["id"]]
            frame = stream.latest()
            if frame is None:
                status_ph.warning("Waiting for frames..." if stream.connected
                                  else f"⚠️ Not connected ({stream.error or 'connecting'})")
                continue

            annotated, violations = engine.analyze(frame, db.get_camera_zone(cam))
            img_ph.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
                         channels="RGB", width="stretch")

            if violations:
                status_ph.error("🚨 " + ", ".join(sorted({v.label for v in violations})))
            else:
                status_ph.success("✅ No violations")

            for v in violations:
                if not alert_mgr.should_alert(cam["id"], v.vtype):
                    continue
                snap = _save_snapshot(annotated, cam["name"], v.vtype)
                phrase = alerts.get_phrase(v.vtype)
                db.log_violation(cam["id"], cam["name"], v.vtype, phrase,
                                 v.confidence, snap)
                cycle_phrases.append(phrase)
                events.insert(0, f"{datetime.now().strftime('%H:%M:%S')} — "
                                 f"**{cam['name']}**: {v.label} → 🔊 \"{phrase}\"")
                st.toast(f"🚨 {cam['name']}: {v.label}", icon="🚨")

        if cycle_phrases and audio_on:
            alerts.speak(cycle_phrases, container=audio_slot)

        del events[30:]
        event_slot.markdown("\n".join(f"- {e}" for e in events) or "_No events yet_")
        time.sleep(float(interval))
