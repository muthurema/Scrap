"""Safety-violation detection engine.

Two model stages, both optional and lazily loaded (the app still runs, in a
degraded mode, if `ultralytics`/model weights are missing):

1. PPE model (``models/ppe.pt`` by default) — a YOLO model trained on a
   construction-safety dataset. Class names are matched by keyword, so any of
   the popular public PPE datasets work out of the box (classes like
   ``NO-Hardhat``, ``NO-Safety Vest``, ``Hardhat``, ``Person`` ...).
2. Pose model (``yolov8n-pose.pt``, auto-downloaded by ultralytics) — used for
   the handrail rule: if a person stands inside the configured stair zone and
   neither wrist is close to the configured rail line, it's a violation.
"""

import math
import os

import cv2
import numpy as np

# Violation type -> (label shown in UI, default spoken phrase)
VIOLATION_TYPES = {
    "no_helmet": ("No helmet", "Wear helmet"),
    "no_vest": ("No safety vest", "Wear safety vest"),
    "no_mask": ("No mask", "Wear mask"),
    "no_handrail": ("Not holding handrail", "Hold handrail"),
}

# Substrings used to map PPE-model class names onto violation types.
_NEGATIVE_CLASS_MAP = {
    "no_helmet": ("no-hardhat", "no_hardhat", "no-helmet", "no_helmet", "nohelmet", "head"),
    "no_vest": ("no-safety vest", "no-vest", "no_vest", "no-safety_vest", "novest"),
    "no_mask": ("no-mask", "no_mask", "nomask"),
}

COLOR_VIOLATION = (40, 40, 230)   # red (BGR)
COLOR_OK = (80, 200, 80)
COLOR_ZONE = (230, 180, 40)


class Violation:
    def __init__(self, vtype, confidence, box=None):
        self.vtype = vtype
        self.confidence = float(confidence)
        self.box = box  # (x1, y1, x2, y2) or None

    @property
    def label(self):
        return VIOLATION_TYPES.get(self.vtype, (self.vtype, ""))[0]


class DetectionEngine:
    """Runs PPE + handrail analysis on frames and returns annotated output."""

    def __init__(self, ppe_model_path="models/ppe.pt",
                 pose_model_path="yolov8n-pose.pt", confidence=0.45):
        self.ppe_model_path = ppe_model_path
        self.pose_model_path = pose_model_path
        self.confidence = confidence
        self._ppe_model = None
        self._pose_model = None
        self._load_attempted = False
        self.status_notes = []

    # ------------------------------------------------------------- loading
    def _load_models(self):
        if self._load_attempted:
            return
        self._load_attempted = True
        try:
            from ultralytics import YOLO
        except ImportError:
            self.status_notes.append(
                "`ultralytics` is not installed — running without AI detection. "
                "Install it with `pip install ultralytics`.")
            return
        if os.path.exists(self.ppe_model_path):
            try:
                self._ppe_model = YOLO(self.ppe_model_path)
            except Exception as exc:
                self.status_notes.append(f"Failed to load PPE model: {exc}")
        else:
            self.status_notes.append(
                f"PPE model not found at `{self.ppe_model_path}` — helmet/vest "
                "detection disabled. See README for where to get weights.")
        try:
            self._pose_model = YOLO(self.pose_model_path)
        except Exception as exc:
            self.status_notes.append(
                f"Pose model unavailable ({exc}) — handrail detection disabled.")

    @property
    def ppe_available(self):
        self._load_models()
        return self._ppe_model is not None

    @property
    def pose_available(self):
        self._load_models()
        return self._pose_model is not None

    # ------------------------------------------------------------ analysis
    def analyze(self, frame, zone_cfg=None):
        """Analyze one frame.

        zone_cfg: {"handrail": {"enabled": bool, "zone": [x1,y1,x2,y2] %,
                                "rail": [x1,y1,x2,y2] %, "threshold": %}}
        Returns (annotated_frame, [Violation, ...]).
        """
        self._load_models()
        annotated = frame.copy()
        violations = []

        if self._ppe_model is not None:
            violations += self._run_ppe(frame, annotated)

        rail_cfg = (zone_cfg or {}).get("handrail") or {}
        if rail_cfg.get("enabled") and self._pose_model is not None:
            violations += self._run_handrail(frame, annotated, rail_cfg)

        return annotated, violations

    def _run_ppe(self, frame, annotated):
        violations = []
        results = self._ppe_model.predict(frame, conf=self.confidence, verbose=False)
        for res in results:
            names = res.names
            for box in res.boxes:
                cls_name = str(names.get(int(box.cls[0]), "")).lower().strip()
                conf = float(box.conf[0])
                xyxy = [int(v) for v in box.xyxy[0].tolist()]
                vtype = None
                for candidate, keywords in _NEGATIVE_CLASS_MAP.items():
                    if any(k in cls_name for k in keywords):
                        vtype = candidate
                        break
                if vtype:
                    violations.append(Violation(vtype, conf, xyxy))
                    self._draw_box(annotated, xyxy, VIOLATION_TYPES[vtype][0], COLOR_VIOLATION, conf)
                elif any(k in cls_name for k in ("hardhat", "helmet", "vest", "mask")):
                    self._draw_box(annotated, xyxy, cls_name, COLOR_OK, conf)
        return violations

    def _run_handrail(self, frame, annotated, cfg):
        h, w = frame.shape[:2]
        zx1, zy1, zx2, zy2 = [v / 100.0 for v in cfg.get("zone", [0, 0, 100, 100])]
        zone_px = (int(zx1 * w), int(zy1 * h), int(zx2 * w), int(zy2 * h))
        rail = cfg.get("rail", [0, 50, 100, 50])
        rail_p1 = (int(rail[0] / 100.0 * w), int(rail[1] / 100.0 * h))
        rail_p2 = (int(rail[2] / 100.0 * w), int(rail[3] / 100.0 * h))
        threshold_px = cfg.get("threshold", 8) / 100.0 * math.hypot(w, h)

        cv2.rectangle(annotated, zone_px[:2], zone_px[2:], COLOR_ZONE, 2)
        cv2.line(annotated, rail_p1, rail_p2, COLOR_ZONE, 2)
        cv2.putText(annotated, "stair zone", (zone_px[0] + 4, zone_px[1] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_ZONE, 1)

        violations = []
        results = self._pose_model.predict(frame, conf=self.confidence, verbose=False)
        for res in results:
            if res.keypoints is None or res.boxes is None:
                continue
            kpts = res.keypoints.xy.cpu().numpy() if hasattr(res.keypoints.xy, "cpu") \
                else np.asarray(res.keypoints.xy)
            for i, box in enumerate(res.boxes):
                xyxy = [int(v) for v in box.xyxy[0].tolist()]
                if not self._box_in_zone(xyxy, zone_px):
                    continue
                conf = float(box.conf[0])
                person_kpts = kpts[i] if i < len(kpts) else None
                holding = False
                if person_kpts is not None and len(person_kpts) > 10:
                    for wrist_idx in (9, 10):  # COCO: left/right wrist
                        wx, wy = person_kpts[wrist_idx][:2]
                        if wx <= 0 and wy <= 0:
                            continue  # keypoint not detected
                        if self._point_to_segment((wx, wy), rail_p1, rail_p2) <= threshold_px:
                            holding = True
                            break
                if holding:
                    self._draw_box(annotated, xyxy, "holding rail", COLOR_OK, conf)
                else:
                    violations.append(Violation("no_handrail", conf, xyxy))
                    self._draw_box(annotated, xyxy, VIOLATION_TYPES["no_handrail"][0],
                                   COLOR_VIOLATION, conf)
        return violations

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _box_in_zone(box, zone):
        bx1, by1, bx2, by2 = box
        zx1, zy1, zx2, zy2 = zone
        ix = max(0, min(bx2, zx2) - max(bx1, zx1))
        iy = max(0, min(by2, zy2) - max(by1, zy1))
        area = max(1, (bx2 - bx1) * (by2 - by1))
        return (ix * iy) / area > 0.3  # >30% of the person inside the zone

    @staticmethod
    def _point_to_segment(p, a, b):
        px, py = float(p[0]), float(p[1])
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    @staticmethod
    def _draw_box(img, xyxy, label, color, conf):
        x1, y1, x2, y2 = xyxy
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(img, text, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1)
