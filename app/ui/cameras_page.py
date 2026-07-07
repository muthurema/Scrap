"""Admin page: register CCTV cameras, verify connections, configure zones."""

import json

import cv2
import streamlit as st

from app import db
from app.camera import verify_connection

SOURCE_TYPES = {
    "rtsp": "RTSP stream (IP camera / NVR)",
    "http": "HTTP/MJPEG stream",
    "webcam": "Local webcam (device index)",
    "file": "Video file (testing)",
    "demo": "Built-in demo feed (no hardware)",
}

SOURCE_HELP = {
    "rtsp": "e.g. rtsp://user:password@192.168.1.64:554/Streaming/Channels/101",
    "http": "e.g. http://192.168.1.64:8080/video",
    "webcam": "Device index, usually 0",
    "file": "Path to a video file, e.g. samples/site.mp4",
    "demo": "Leave as `demo` — generates a synthetic feed",
}


def _status_badge(camera):
    status = camera.get("last_status") or "never_tested"
    when = camera.get("last_verified_at") or ""
    if status == "online":
        st.success(f"✅ Verified online {when}")
    elif status == "never_tested":
        st.info("⚪ Connection not tested yet")
    else:
        st.error(f"❌ {status} (last checked {when})")


def _test_and_show(camera):
    with st.spinner(f"Connecting to **{camera['name']}** ..."):
        ok, message, frame = verify_connection(camera["source"], camera["source_type"])
    db.set_camera_status(camera["id"], "online" if ok else f"offline: {message}")
    if ok:
        st.success(message)
        if frame is not None:
            st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                     caption="Snapshot from the camera", width=420)
    else:
        st.error(message)


def _zone_editor(camera):
    zone = db.get_camera_zone(camera)
    rail_cfg = zone.get("handrail") or {}
    st.markdown(
        "Enable this for cameras watching **stairways**. Mark the stair area and the "
        "handrail line as percentages of the frame; a person inside the area whose "
        "hands are away from the rail triggers a *Hold handrail* alert.")
    enabled = st.checkbox("Enable handrail monitoring", value=bool(rail_cfg.get("enabled")),
                          key=f"hr_en_{camera['id']}")
    z = rail_cfg.get("zone", [10, 30, 90, 95])
    r = rail_cfg.get("rail", [15, 45, 85, 60])
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Stair zone (rectangle, % of frame)")
        zx = st.slider("Zone left / right %", 0, 100, (int(z[0]), int(z[2])), key=f"zx_{camera['id']}")
        zy = st.slider("Zone top / bottom %", 0, 100, (int(z[1]), int(z[3])), key=f"zy_{camera['id']}")
    with c2:
        st.caption("Handrail line (two endpoints, % of frame)")
        rx1 = st.slider("Rail start X %", 0, 100, int(r[0]), key=f"rx1_{camera['id']}")
        ry1 = st.slider("Rail start Y %", 0, 100, int(r[1]), key=f"ry1_{camera['id']}")
        rx2 = st.slider("Rail end X %", 0, 100, int(r[2]), key=f"rx2_{camera['id']}")
        ry2 = st.slider("Rail end Y %", 0, 100, int(r[3]), key=f"ry2_{camera['id']}")
    threshold = st.slider("Hand-to-rail distance tolerance (% of frame diagonal)", 2, 20,
                          int(rail_cfg.get("threshold", 8)), key=f"thr_{camera['id']}")
    if st.button("💾 Save zone", key=f"save_zone_{camera['id']}"):
        zone["handrail"] = {
            "enabled": enabled,
            "zone": [zx[0], zy[0], zx[1], zy[1]],
            "rail": [rx1, ry1, rx2, ry2],
            "threshold": threshold,
        }
        db.update_camera(camera["id"], zone_json=json.dumps(zone))
        st.success("Zone saved.")
        st.rerun()

    if st.button("👁 Preview zone on snapshot", key=f"prev_{camera['id']}"):
        ok, msg, frame = verify_connection(camera["source"], camera["source_type"])
        if ok and frame is not None:
            h, w = frame.shape[:2]
            p = lambda vx, vy: (int(vx / 100 * w), int(vy / 100 * h))
            cv2.rectangle(frame, p(zx[0], zy[0]), p(zx[1], zy[1]), (230, 180, 40), 2)
            cv2.line(frame, p(rx1, ry1), p(rx2, ry2), (40, 40, 230), 3)
            st.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                     caption="Yellow = stair zone, red = handrail line", width=560)
        else:
            st.error(f"Could not grab a snapshot: {msg}")


def render():
    st.title("🎥 Camera administration")
    st.caption("Register CCTV cameras, verify their connections and configure detection zones.")

    # ---------------------------------------------------------- add camera
    with st.expander("➕ Add a new camera", expanded=not db.list_cameras()):
        with st.form("add_camera", clear_on_submit=True):
            name = st.text_input("Camera name *", placeholder="Warehouse entrance")
            location = st.text_input("Location", placeholder="Building A, floor 2")
            source_type = st.selectbox(
                "Source type", list(SOURCE_TYPES), format_func=SOURCE_TYPES.get)
            source = st.text_input("Source / URL *", help="; ".join(SOURCE_HELP.values()),
                                   placeholder=SOURCE_HELP[source_type])
            enabled = st.checkbox("Enabled for monitoring", value=True)
            test_first = st.checkbox("Verify connection before saving", value=True)
            submitted = st.form_submit_button("Add camera", type="primary")
        if submitted:
            if source_type == "demo" and not source:
                source = "demo"
            if not name or not source:
                st.error("Name and source are required.")
            else:
                if test_first:
                    ok, message, frame = verify_connection(source, source_type)
                    if ok:
                        st.success(f"Verified: {message}")
                    else:
                        st.warning(f"Saved anyway, but the connection test failed: {message}")
                cam_id = db.add_camera(name, source, source_type, location, enabled)
                if test_first:
                    db.set_camera_status(cam_id, "online" if ok else f"offline: {message}")
                st.success(f"Camera **{name}** added.")
                st.rerun()

    # --------------------------------------------------------- camera list
    cameras = db.list_cameras()
    if not cameras:
        st.info("No cameras registered yet. Add one above — use the built-in **demo feed** "
                "to try the app without hardware.")
        return

    st.subheader(f"Registered cameras ({len(cameras)})")
    if st.button("🔌 Verify all connections"):
        results = []
        progress = st.progress(0.0)
        for i, cam in enumerate(cameras):
            ok, message, _ = verify_connection(cam["source"], cam["source_type"])
            db.set_camera_status(cam["id"], "online" if ok else f"offline: {message}")
            results.append((cam["name"], ok, message))
            progress.progress((i + 1) / len(cameras))
        progress.empty()
        for cam_name, ok, message in results:
            (st.success if ok else st.error)(f"**{cam_name}** — {message}")
        st.rerun()

    for cam in cameras:
        icon = "🟢" if cam["last_status"] == "online" else \
               ("⚪" if cam["last_status"] == "never_tested" else "🔴")
        with st.expander(f"{icon} {cam['name']} — {SOURCE_TYPES.get(cam['source_type'], cam['source_type'])}"
                         f"{' · ' + cam['location'] if cam['location'] else ''}"):
            _status_badge(cam)
            tab_details, tab_zone, tab_danger = st.tabs(["Details & test", "Handrail zone", "Remove"])

            with tab_details:
                with st.form(f"edit_{cam['id']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        new_name = st.text_input("Name", cam["name"])
                        new_loc = st.text_input("Location", cam["location"] or "")
                    with c2:
                        new_type = st.selectbox("Source type", list(SOURCE_TYPES),
                                                index=list(SOURCE_TYPES).index(cam["source_type"]),
                                                format_func=SOURCE_TYPES.get)
                        new_source = st.text_input("Source / URL", cam["source"])
                    new_enabled = st.checkbox("Enabled for monitoring", value=bool(cam["enabled"]))
                    if st.form_submit_button("Save changes"):
                        db.update_camera(cam["id"], name=new_name, location=new_loc,
                                         source=new_source, source_type=new_type,
                                         enabled=int(new_enabled))
                        st.success("Saved.")
                        st.rerun()
                if st.button("🔌 Test connection", key=f"test_{cam['id']}", type="primary"):
                    _test_and_show(cam)

            with tab_zone:
                _zone_editor(cam)

            with tab_danger:
                st.warning("Removing a camera keeps its violation history but stops monitoring it.")
                if st.button(f"🗑 Delete '{cam['name']}'", key=f"del_{cam['id']}"):
                    db.delete_camera(cam["id"])
                    st.rerun()
