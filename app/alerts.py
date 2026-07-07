"""Immediate audio alerts (browser text-to-speech) with per-camera cooldowns."""

import html
import json
import time

import streamlit.components.v1 as components

from app import db
from app.detection.engine import VIOLATION_TYPES

DEFAULT_COOLDOWN_SECONDS = 15


def get_phrase(vtype: str) -> str:
    """Spoken phrase for a violation type (admin-overridable in Settings)."""
    stored = db.get_setting(f"phrase_{vtype}")
    if stored:
        return stored
    return VIOLATION_TYPES.get(vtype, (vtype, vtype.replace("_", " ")))[1]


def audio_enabled() -> bool:
    return db.get_setting("audio_enabled", "1") == "1"


def get_cooldown() -> int:
    try:
        return int(db.get_setting("alert_cooldown", DEFAULT_COOLDOWN_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS


class AlertManager:
    """Debounces repeated alerts: the same violation on the same camera is
    only announced/logged again after the cooldown expires."""

    def __init__(self, cooldown_seconds=None):
        self.cooldown = cooldown_seconds or get_cooldown()
        self._last = {}

    def should_alert(self, camera_id, vtype) -> bool:
        key = (camera_id, vtype)
        now = time.time()
        if now - self._last.get(key, 0) >= self.cooldown:
            self._last[key] = now
            return True
        return False


def speak(phrases, container=None):
    """Speak phrases out loud in the operator's browser via SpeechSynthesis.

    Runs entirely client-side, so it works with no extra server dependencies
    and no internet access. `container` should be an st.empty() slot when
    called repeatedly inside a monitoring loop.
    """
    if not phrases:
        return
    safe = json.dumps([html.escape(str(p)) for p in phrases])
    # `time.time()` in the payload makes each render unique so the browser
    # re-executes the script on every alert.
    code = f"""
    <script>
    (function() {{
        const phrases = {safe};  // render {time.time()}
        const speakAll = () => {{
            window.speechSynthesis.cancel();
            phrases.forEach((text) => {{
                const u = new SpeechSynthesisUtterance(text);
                u.rate = 1.0; u.pitch = 1.0; u.volume = 1.0; u.lang = 'en-US';
                window.speechSynthesis.speak(u);
            }});
        }};
        speakAll();
    }})();
    </script>
    """
    if container is not None:
        with container:
            components.html(code, height=0)
    else:
        components.html(code, height=0)
