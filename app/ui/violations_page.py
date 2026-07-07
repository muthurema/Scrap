"""Violation history: filters, snapshots and CSV export."""

import csv
import io
import os
from datetime import date, datetime, timedelta

import streamlit as st

from app import db
from app.detection.engine import VIOLATION_TYPES


def render():
    st.title("📋 Violation history")

    cameras = db.list_cameras()
    cam_names = {c["id"]: c["name"] for c in cameras}

    c1, c2, c3 = st.columns(3)
    with c1:
        cam_filter = st.selectbox("Camera", [None] + list(cam_names),
                                  format_func=lambda v: "All cameras" if v is None else cam_names[v])
    with c2:
        type_filter = st.selectbox("Violation type", [None] + list(VIOLATION_TYPES),
                                   format_func=lambda v: "All types" if v is None
                                   else VIOLATION_TYPES[v][0])
    with c3:
        days = st.selectbox("Period", [1, 7, 30, 365], index=1,
                            format_func=lambda d: f"Last {d} day(s)")

    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.list_violations(camera_id=cam_filter, vtype=type_filter, since=since)

    counts = db.violation_counts_by_type(since=since)
    if counts:
        cols = st.columns(max(len(counts), 1))
        for col, (vtype, n) in zip(cols, counts.items()):
            col.metric(VIOLATION_TYPES.get(vtype, (vtype,))[0], n)

    if not rows:
        st.info("No violations recorded for the selected filters. 🎉")
        return

    # CSV export
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "camera", "violation", "announcement", "confidence"])
    for r in rows:
        writer.writerow([r["created_at"], r["camera_name"],
                         VIOLATION_TYPES.get(r["vtype"], (r["vtype"],))[0],
                         r["message"], f"{r['confidence']:.2f}"])
    st.download_button("⬇️ Export CSV", buf.getvalue(),
                       file_name=f"violations_{date.today()}.csv", mime="text/csv")

    st.caption(f"{len(rows)} record(s)")
    for r in rows[:200]:
        label = VIOLATION_TYPES.get(r["vtype"], (r["vtype"],))[0]
        with st.expander(f"🚨 {r['created_at']} — {r['camera_name']} — {label}"):
            c1, c2 = st.columns([2, 3])
            with c1:
                st.write(f"**Camera:** {r['camera_name']}")
                st.write(f"**Violation:** {label}")
                st.write(f"**Announcement:** 🔊 \"{r['message']}\"")
                if r["confidence"]:
                    st.write(f"**Confidence:** {r['confidence']:.0%}")
            with c2:
                if r["snapshot_path"] and os.path.exists(r["snapshot_path"]):
                    st.image(r["snapshot_path"], caption="Snapshot at detection time")
                else:
                    st.caption("No snapshot available.")
