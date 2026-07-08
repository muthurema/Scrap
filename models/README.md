# Model weights

The app can download a PPE model for you: **Settings → Detection →
Download PPE model** (saved here as `ppe.pt`). Alternatively, place your
own PPE detection model here as `ppe.pt` (path configurable in the app's
**Settings** page).

Any YOLO model trained on a construction-safety / PPE dataset works — class
names are matched by keyword (`NO-Hardhat`, `NO-Safety Vest`, `NO-Mask`,
`Hardhat`, `Safety Vest`, ...). See the main README for suggested sources.

The pose model used for handrail detection (`yolov8n-pose.pt`) is downloaded
automatically by `ultralytics` on first use.
