"""Automatic download of detection model weights.

Public, ready-to-use YOLOv8 checkpoints are fetched straight from their
official hosting (Hugging Face / ultralytics GitHub releases). Every source
is tried in order until one succeeds, so a single mirror being down doesn't
break setup.
"""

import os
import shutil
import tempfile
import urllib.request

# Candidate PPE models, best first. All are standard YOLOv8 checkpoints whose
# class names match the keyword mapping in engine.py.
PPE_MODEL_CHOICES = {
    "hard_hat_m": {
        "label": "Hard-hat detection, medium (recommended) — classes: Hardhat / NO-Hardhat",
        "urls": [
            "https://huggingface.co/keremberke/yolov8m-hard-hat-detection/resolve/main/best.pt",
        ],
    },
    "hard_hat_s": {
        "label": "Hard-hat detection, small (faster on CPU) — classes: Hardhat / NO-Hardhat",
        "urls": [
            "https://huggingface.co/keremberke/yolov8s-hard-hat-detection/resolve/main/best.pt",
        ],
    },
    "ppe_full_m": {
        "label": "Protective-equipment detection, medium — helmet / mask / more classes",
        "urls": [
            "https://huggingface.co/keremberke/yolov8m-protective-equipment-detection/resolve/main/best.pt",
        ],
    },
}

POSE_MODEL_URLS = [
    # ultralytics auto-downloads this itself; these are explicit fallbacks.
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt",
    "https://ultralytics.com/assets/yolov8n-pose.pt",
]

_MIN_VALID_SIZE = 1_000_000  # a real checkpoint is many MB; catches HTML error pages


def _fetch(url: str, dest: str, progress_cb=None, timeout: int = 60) -> None:
    """Download url -> dest atomically (temp file + rename)."""
    req = urllib.request.Request(url, headers={"User-Agent": "SafetyWatch/1.0"})
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dest) or ".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(done / total, 1.0))
        if os.path.getsize(tmp_path) < _MIN_VALID_SIZE:
            raise IOError("downloaded file is too small to be a model checkpoint")
        shutil.move(tmp_path, dest)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def download_from_candidates(urls, dest, progress_cb=None):
    """Try each URL until one produces a valid file.

    Returns (ok: bool, message: str).
    """
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    errors = []
    for url in urls:
        try:
            _fetch(url, dest, progress_cb)
            size_mb = os.path.getsize(dest) / 1e6
            return True, f"Downloaded {size_mb:.1f} MB from {url.split('/')[2]}"
        except Exception as exc:
            errors.append(f"{url.split('/')[2]}: {exc}")
    return False, "All sources failed — " + "; ".join(errors)


def download_ppe_model(choice: str, dest: str, progress_cb=None):
    cfg = PPE_MODEL_CHOICES.get(choice)
    if not cfg:
        return False, f"Unknown model choice '{choice}'"
    return download_from_candidates(cfg["urls"], dest, progress_cb)


def download_pose_model(dest: str = "yolov8n-pose.pt", progress_cb=None):
    if os.path.exists(dest):
        return True, "Pose model already present."
    return download_from_candidates(POSE_MODEL_URLS, dest, progress_cb)


def ensure_models(ppe_path: str, ppe_choice: str = "hard_hat_m"):
    """Fetch any missing models. Returns a list of human-readable results."""
    results = []
    if not os.path.exists(ppe_path):
        ok, msg = download_ppe_model(ppe_choice, ppe_path)
        results.append(("PPE model", ok, msg))
    if not os.path.exists("yolov8n-pose.pt"):
        ok, msg = download_pose_model()
        results.append(("Pose model", ok, msg))
    return results
