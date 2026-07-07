"""Camera connectivity: connection verification and threaded frame readers.

Supported sources:
  - RTSP / HTTP(S) stream URLs (typical CCTV / IP cameras, e.g. rtsp://user:pass@ip:554/stream)
  - Local webcam device index ("0", "1", ...)
  - Video file path (useful for testing without hardware)
  - "demo" — a synthetic generated feed so the pipeline can be tried with no camera at all
"""

import threading
import time

import cv2
import numpy as np


def _resolve_source(source: str, source_type: str):
    if source_type == "webcam":
        try:
            return int(source)
        except (TypeError, ValueError):
            return 0
    return source


def verify_connection(source: str, source_type: str, timeout: float = 8.0):
    """Try to open the stream and grab one frame.

    Returns (ok: bool, message: str, frame: np.ndarray | None).
    """
    if source_type == "demo":
        return True, "Demo source is always available.", _demo_frame(0)

    resolved = _resolve_source(source, source_type)
    cap = None
    try:
        cap = cv2.VideoCapture(resolved)
        if source_type in ("rtsp", "http"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            return False, "Could not open the stream. Check the URL, credentials and network reachability.", None
        deadline = time.time() + timeout
        while time.time() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                h, w = frame.shape[:2]
                return True, f"Connection OK — receiving {w}x{h} video.", frame
            time.sleep(0.2)
        return False, "Stream opened but no frames arrived within the timeout.", None
    except Exception as exc:  # pragma: no cover - depends on backend
        return False, f"Connection error: {exc}", None
    finally:
        if cap is not None:
            cap.release()


def _demo_frame(tick: int, size=(480, 854)):
    """Synthetic frame with a moving marker, used by the built-in demo source."""
    h, w = size
    frame = np.full((h, w, 3), 34, dtype=np.uint8)
    for y in range(0, h, 40):
        cv2.line(frame, (0, y), (w, y), (48, 48, 48), 1)
    x = int((np.sin(tick / 20.0) * 0.4 + 0.5) * w)
    cv2.circle(frame, (x, h // 2), 28, (60, 140, 230), -1)
    cv2.putText(frame, "DEMO FEED (no camera connected)", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
    return frame


class CameraStream:
    """Background thread that keeps only the most recent frame of a stream.

    Reading in a thread avoids RTSP buffer lag: analysis always sees the
    newest frame instead of a stale, queued one.
    """

    def __init__(self, camera: dict):
        self.camera = camera
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._tick = 0
        self.connected = False
        self.error = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    # ------------------------------------------------------------------
    def _run(self):
        if self.camera["source_type"] == "demo":
            self.connected = True
            while not self._stop.is_set():
                with self._lock:
                    self._frame = _demo_frame(self._tick)
                self._tick += 1
                time.sleep(1 / 15)
            return

        resolved = _resolve_source(self.camera["source"], self.camera["source_type"])
        while not self._stop.is_set():
            cap = cv2.VideoCapture(resolved)
            if self.camera["source_type"] in ("rtsp", "http"):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                self.connected = False
                self.error = "unable to open stream"
                cap.release()
                if self._stop.wait(3):
                    return
                continue
            self.connected = True
            self.error = ""
            failures = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures > 25:  # stream died — reconnect
                        self.connected = False
                        self.error = "stream interrupted, reconnecting"
                        break
                    time.sleep(0.05)
                    continue
                failures = 0
                # Loop video files for continuous testing.
                if self.camera["source_type"] == "file":
                    pass
                with self._lock:
                    self._frame = frame
            cap.release()
            if self.camera["source_type"] == "file" and not self._stop.is_set():
                continue  # restart the file from the beginning
