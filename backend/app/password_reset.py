"""
Password reset service.

Self-service flow:
  1. POST /api/auth/password-reset/request — user gives email; we generate
     a 32-byte URL-safe token, store its SHA-256 hash in Mongo (raw token
     is never persisted), email a magic link, return 200 always (anti-
     enumeration: the response is identical whether the email exists).
  2. User clicks the magic link → /reset-password?token=<raw>
  3. POST /api/auth/password-reset/confirm — frontend submits the raw
     token + new password; we hash the token, look it up, validate
     not-expired AND not-used, rotate the user's bcrypt hash, mark the
     row consumed (and Mongo's TTL index sweeps it on expiry).

Hardening:
  * Tokens are 32 random bytes (~256 bits of entropy)
  * Only sha256(token) is stored — Mongo leak doesn't yield usable links
  * Rate-limit: max 5 active (non-expired) requests per email per hour
  * Email delivery via stdlib smtplib in `asyncio.to_thread` (non-blocking)
  * SMTP is best-effort: a delivery failure should NOT leak account state
    to the requester, so we log + still return 200
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from app.db import password_resets_col

logger = logging.getLogger("ehs-rag")

TOKEN_TTL_MINUTES = int(os.environ.get("PASSWORD_RESET_TTL_MIN", "15"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("PASSWORD_RESET_RATE_LIMIT", "5"))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_reset_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex). Raw is sent in the email link;
    only the hash is persisted in Mongo."""
    raw = secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


async def is_rate_limited(email: str) -> bool:
    """True if this email has more than RATE_LIMIT_PER_HOUR active
    (non-consumed, non-expired) reset rows in the last hour."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    n = await password_resets_col().count_documents({
        "email": email,
        "created_at": {"$gte": cutoff.isoformat()},
    })
    return n >= RATE_LIMIT_PER_HOUR


async def create_reset_record(email: str, user_id: str) -> str:
    """Persist a new reset row, return the RAW token (caller emails it)."""
    raw, hashed = generate_reset_token()
    now = datetime.now(timezone.utc)
    await password_resets_col().insert_one({
        "id": str(uuid.uuid4()),
        "email": email,
        "user_id": user_id,
        "token_hash": hashed,
        "created_at": now.isoformat(),
        # Use a datetime (not iso) for the TTL field — Mongo's
        # expireAfterSeconds index requires a BSON date.
        "expires_at": now + timedelta(minutes=TOKEN_TTL_MINUTES),
        "consumed_at": None,
        "consumed_ip": None,
    })
    return raw


async def consume_reset_token(raw_token: str) -> dict | None:
    """Look up a reset row by hashed token. Returns the row if it's valid
    (not expired, not consumed) — else None. Marks it consumed in the
    same call (idempotent: a second consume attempt returns None)."""
    if not raw_token:
        return None
    hashed = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    # findOneAndUpdate so the read + consume are atomic — defeats a
    # double-click race or a parallel attacker reusing the link.
    row = await password_resets_col().find_one_and_update(
        {
            "token_hash": hashed,
            "consumed_at": None,
            "expires_at": {"$gt": now},
        },
        {"$set": {"consumed_at": now.isoformat()}},
    )
    return row


# ── SMTP delivery (stdlib, run in threadpool) ────────────────────────────────

def _send_smtp_sync(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    """Blocking SMTP send. Call via asyncio.to_thread.

    Reads connection settings from env (set in Railway):
      SMTP_HOST, SMTP_PORT (default 587), SMTP_USERNAME, SMTP_PASSWORD,
      SMTP_FROM (sender), SMTP_USE_TLS ("true"/"false", default true)
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    sender = os.environ.get("SMTP_FROM", username).strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in ("0", "false", "no")

    if not host or not username or not password:
        # In dev / when SMTP isn't configured, fall back to console logging
        # so engineers can still test the flow.
        logger.warning(
            f"[smtp] NOT CONFIGURED — SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD "
            f"missing. Would have sent to {to_email}.\n  Subject: {subject}\n"
            f"  Plain body:\n{text_body}"
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    # Positive-confirmation log so success is visible in Railway logs
    # (otherwise a silent send looks identical to a silent failure when
    # the user reports "no email arrived").
    logger.info(
        f"[smtp] sending → host={host}:{port} from={sender} to={to_email} "
        f"use_tls={use_tls} mode={'SSL' if port == 465 else 'STARTTLS' if use_tls else 'plain'}"
    )

    if port == 465:
        # SMTPS (implicit TLS)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
            s.login(username, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            if use_tls:
                s.starttls(context=ssl.create_default_context())
            s.login(username, password)
            s.send_message(msg)

    logger.info(f"[smtp] delivered to {to_email}")


async def send_reset_email(to_email: str, reset_url: str, expires_min: int) -> None:
    subject = "Reset your CIDSA RAG password"
    text_body = (
        f"Hi,\n\n"
        f"We received a request to reset the password for this email address. "
        f"Click the link below to set a new password — it expires in "
        f"{expires_min} minutes.\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email — "
        f"your password will not change.\n\n"
        f"— CIDSA RAG"
    )
    html_body = f"""\
<!doctype html>
<html><body style="font-family: system-ui, -apple-system, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1e293b;">
  <div style="font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase; color: #64748b; margin-bottom: 8px;">CIDSA RAG</div>
  <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 16px;">Reset your password</h1>
  <p style="line-height: 1.6;">We received a request to reset the password for this email address. Click the button below to set a new password — it expires in <strong>{expires_min} minutes</strong>.</p>
  <p style="margin: 32px 0;">
    <a href="{reset_url}" style="background: #059669; color: #ffffff; padding: 12px 24px; text-decoration: none; font-weight: 600; display: inline-block;">Set new password</a>
  </p>
  <p style="font-size: 12px; color: #64748b; line-height: 1.6;">Or paste this link into your browser:<br><span style="word-break: break-all;">{reset_url}</span></p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 32px 0;">
  <p style="font-size: 12px; color: #94a3b8;">If you didn't request this, you can safely ignore this email — your password won't change.</p>
</body></html>"""
    try:
        await asyncio.to_thread(_send_smtp_sync, to_email, subject, html_body, text_body)
    except Exception as e:
        # Never let SMTP failure bubble to the caller — that would leak
        # account existence to whoever requested the reset. We DO log
        # the full traceback so the operator can diagnose from Railway
        # logs (`railway logs --service=backend | grep smtp`).
        logger.exception(
            f"[smtp] FAILED to deliver reset link to {to_email}: "
            f"{type(e).__name__}: {e}"
        )
