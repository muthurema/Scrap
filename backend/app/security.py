"""
Security: prompt injection sanitization, SSRF protection, secret masking, audit log helper.
"""
import re
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional
from loguru import logger


# ── Prompt-injection patterns ────────────────────────────────────────────────

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|messages?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above|earlier)",
    r"forget\s+(everything|all|previous|prior)",
    r"</?\s*(system|instructions?|admin|assistant)\s*>",
    r"\[\s*(system|admin|instructions?|sudo)\s*\]",
    r"new\s+(instructions?|system\s+prompt|directives?)\s*:",
    r"you\s+are\s+(now|actually|really)\s+(a|an)\s+",
    r"act\s+as\s+(if|though|a|an)\s+",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"reveal\s+(your|the)\s+(system\s+prompt|instructions|hidden)",
    r"print\s+(your|the)\s+(system\s+prompt|instructions)",
    r"output\s+(everything|all)\s+(above|in\s+your\s+context)",
    r"<\s*\|.*?\|\s*>",  # ChatML-style tokens like <|im_start|>
]
INJECTION_REGEX = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)


def has_injection_signal(text: str) -> bool:
    """True if text shows characteristics of a prompt-injection attempt."""
    if not text:
        return False
    return INJECTION_REGEX.search(text) is not None


def sanitize_user_query(text: str) -> str:
    """
    Light cleaning of user input before sending to LLM:
    - Strip ChatML / OpenAI-style special tokens
    - Strip role-tag XML
    - Collapse excessive whitespace
    Does NOT remove the words themselves — the system prompt is trained to ignore them,
    but we make injection harder by removing the structural anchors.
    """
    if not text:
        return ""
    # Drop ChatML tokens
    text = re.sub(r"<\s*\|[^|]*\|\s*>", " ", text)
    # Drop role tags
    text = re.sub(r"</?\s*(system|assistant|instructions?)\s*>", " ", text, flags=re.IGNORECASE)
    # Collapse newlines / spaces
    text = re.sub(r"\s+", " ", text).strip()
    # Cap length defensively (route also enforces; double-belt)
    return text[:5000]


def scan_document_for_injection(text: str, max_findings: int = 5) -> list[str]:
    """
    Scan an ingested document for embedded prompt-injection payloads.
    Returns a list of matched snippets (for logging / admin review).
    """
    findings: list[str] = []
    if not text:
        return findings
    for m in INJECTION_REGEX.finditer(text):
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        findings.append(text[start:end].strip())
        if len(findings) >= max_findings:
            break
    return findings


# ── SSRF protection ──────────────────────────────────────────────────────────

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),       # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),         # multicast
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_ALLOWED_SCHEMES = {"http", "https"}


def is_safe_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validate a URL is safe to fetch (SSRF-protected).
    Returns (is_safe, error_message_if_unsafe).
    """
    if not url or len(url) > 2048:
        return False, "URL is empty or too long"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' not allowed (only http/https)"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "URL is missing hostname"

    # Block direct localhost / metadata references
    blocked_hosts = {"localhost", "metadata.google.internal", "metadata"}
    if host in blocked_hosts:
        return False, f"Host '{host}' is blocked"

    # Resolve and check every IP for the host
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"

    for family, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return False, f"Host resolves to private/reserved IP {ip_str}"
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            return False, f"Host resolves to disallowed IP {ip_str}"

    return True, None


# ── Secret masking for logs ───────────────────────────────────────────────────

_SECRET_PATTERNS = [
    (re.compile(r"(sk-emergent-[A-Za-z0-9]+)"), "sk-emergent-***"),
    (re.compile(r"(sk-ant-[A-Za-z0-9_\-]+)"), "sk-ant-***"),
    (re.compile(r"(sk-[A-Za-z0-9]{20,})"), "sk-***"),
    (re.compile(r"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"), "<jwt:***>"),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ── PII heuristic (very light) ───────────────────────────────────────────────

_PII_PATTERNS = {
    "email": re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
}


def detect_pii(text: str) -> list[str]:
    """Return a list of PII categories detected (heuristic only)."""
    return [name for name, pat in _PII_PATTERNS.items() if pat.search(text or "")]
