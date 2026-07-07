"""Dashboard: system overview — cameras, connection health, recent violations."""

from datetime import datetime, timedelta

import streamlit as st

from app import db
from app.detection.engine import VIOLATION_TYPES


def render():
    st.title("🦺 SafetyWatch dashboard")
    st.caption("AI safety monitoring for CCTV: PPE compliance, handrail use and instant voice alerts.")

    cameras = db.list_cameras()
    online = [c for c in cameras if c["last_status"] == "online"]
    since_24h = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    recent = db.list_violations(since=since_24h, limit=1000)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cameras registered", len(cameras))
    c2.metric("Verified online", len(online))
    c3.metric("Violations (24 h)", len(recent))
    counts = db.violation_counts_by_type(since=since_24h)
    top = max(counts, key=counts.get) if counts else None
    c4.metric("Most frequent (24 h)", VIOLATION_TYPES.get(top, (top,))[0] if top else "—")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("📷 Cameras")
        if not cameras:
            st.info("No cameras yet — go to **Camera administration** to add your CCTV "
                    "cameras (or the built-in demo feed).")
        for cam in cameras:
            icon = {"online": "🟢"}.get(cam["last_status"], "⚪" if cam["last_status"] == "never_tested" else "🔴")
            status = cam["last_status"] if cam["last_status"] != "never_tested" else "not tested"
            st.markdown(f"{icon} **{cam['name']}**"
                        f"{' · ' + cam['location'] if cam['location'] else ''} — "
                        f"{'enabled' if cam['enabled'] else 'disabled'}, {status}")

    with right:
        st.subheader("🚨 Latest violations (24 h)")
        if not recent:
            st.success("No violations in the last 24 hours.")
        for r in recent[:10]:
            label = VIOLATION_TYPES.get(r["vtype"], (r["vtype"],))[0]
            st.markdown(f"- `{r['created_at'][11:19]}` **{r['camera_name']}** — {label} "
                        f"(🔊 \"{r['message']}\")")

    st.divider()
    st.markdown(
        "**Quick start:** 1️⃣ Add cameras in *Camera administration* and use **Test "
        "connection** to verify each one → 2️⃣ configure the handrail zone for stairway "
        "cameras → 3️⃣ open *Live monitoring* and press **Start**. Keep that tab open "
        "and unmuted: voice alerts (\"Wear helmet\", \"Hold handrail\", ...) play there "
        "the moment a violation is detected.")
