"""
High-risk topic detection + escalation banner.
"""
import re

HIGH_RISK_PATTERNS = [
    r"chemical\s+(spill|release|leak|exposure)",
    r"fire|explosion|deton",
    r"emergency\s+(response|evacuation)|evacuation",
    r"fatal|death|fatality|killed",
    r"injury|injured|bleeding|amputat|burn(?:ed|ing)?",
    r"immediate\s+danger|life[-\s]?threatening|imminent",
    r"H2S|hydrogen\s+sulfide|hydrogen\s+sulphide",
    r"electrocut|electric\s+shock|arc\s+flash",
    r"collapse|trapped|fall(?:en)?\s+from",
    r"toxic\s+gas|gas\s+leak",
    r"unconscious|not\s+breathing|cardiac\s+arrest",
]
HIGH_RISK_REGEX = re.compile("|".join(f"(?:{p})" for p in HIGH_RISK_PATTERNS), re.IGNORECASE)

ESCALATION_BANNER = (
    "⚠️ **Immediate safety concern detected.** "
    "If this is an active emergency, **stop and contact your EHS officer or emergency services NOW**. "
    "The information below is general guidance, not a substitute for live professional response."
)


def is_high_risk(query: str) -> bool:
    return bool(HIGH_RISK_REGEX.search(query or ""))
