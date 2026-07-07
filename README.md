# 🦺 SafetyWatch — CCTV safety-violation monitoring

Connect your CCTV cameras, detect safety violations with AI (no helmet, no
safety vest, not holding the handrail on stairs, ...) and get an **instant
voice announcement** — *"Wear helmet"*, *"Hold handrail"* — the moment a
violation is spotted.

## Features

- **Multi-camera admin panel** — register any number of cameras: RTSP (IP
  cameras / NVRs), HTTP/MJPEG streams, local webcams, video files, or a
  built-in demo feed for trying the app without hardware.
- **Connection verification** — one-click *Test connection* per camera (and
  *Verify all*): opens the stream, grabs a snapshot and records the
  online/offline status with a timestamp.
- **AI violation detection**
  - PPE compliance (helmet / safety vest / mask) via a YOLO model trained on
    construction-safety data.
  - Handrail rule via pose estimation: mark the stair zone and rail line per
    camera; a person on the stairs whose hands are away from the rail
    triggers *"Hold handrail"*.
- **Immediate audio alerts** — spoken in the operator's browser using
  text-to-speech (works offline, phrases are editable in Settings), with a
  per-camera / per-violation cooldown so alerts don't spam.
- **Violation history** — every alert is logged with a snapshot; filter by
  camera / type / period and export to CSV.
- **Admin login** — password-protected (default `admin123`, change it in
  Settings on first run).

## Quick start

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

1. Sign in with the default password `admin123` (then change it in **Settings**).
2. **Camera administration** → *Add a new camera*. For an IP camera use its
   RTSP URL, e.g. `rtsp://user:password@192.168.1.64:554/Streaming/Channels/101`.
   No camera handy? Pick the **built-in demo feed**.
3. Click **Test connection** — you'll get a live snapshot if the camera is
   reachable, or a clear error if not.
4. For stairway cameras, open the **Handrail zone** tab, enable monitoring and
   position the stair zone + rail line (with snapshot preview).
5. Open **Live monitoring** and press **Start**. Keep the tab open and
   unmuted at the operator station — voice alerts play there instantly.

## PPE model weights

Helmet/vest detection needs a YOLO model trained on PPE data. Place the
weights at `models/ppe.pt` (path configurable in Settings). Class names are
matched by keyword, so any of the popular public models work, e.g.:

- Roboflow *Construction Site Safety* YOLOv8 models
  (classes `Hardhat`, `NO-Hardhat`, `Safety Vest`, `NO-Safety Vest`, ...)
- Hugging Face hard-hat detection YOLOv8 checkpoints
- Your own model trained with `ultralytics` on your site's footage
  (recommended for best accuracy)

The handrail feature uses `yolov8n-pose.pt`, which ultralytics downloads
automatically on first use. Without any model files the app still runs
(camera admin, verification, demo feed) — detection simply reports itself
as unavailable on the monitoring page.

## Architecture

```
streamlit_app.py          entry point: login + navigation
app/
  db.py                   SQLite (cameras, violations, settings)
  auth.py                 admin password (PBKDF2)
  camera.py               connection verification + threaded stream readers
  alerts.py               voice alerts (browser TTS) + cooldown logic
  detection/engine.py     YOLO PPE + pose-based handrail detection
  ui/                     dashboard, camera admin, live monitor, history, settings
data/                     SQLite DB + violation snapshots (created at runtime)
models/                   put ppe.pt here
```

## Notes

- Audio plays in the browser tab running **Live monitoring** — use the
  machine/speakers at your control room. Browsers may require one user
  interaction (the Start click counts) before allowing sound.
- Analysis frequency, detection confidence and alert cooldown are tunable in
  **Settings** / on the monitoring page.
