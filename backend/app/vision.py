"""
Claude vision integration via emergentintegrations.

Used when the chat input has image attachments. Combines retrieved RAG context (text) with
the user's images in a single Claude Sonnet 4.6 call and returns the full answer text.
Streaming is intentionally not used for the vision path — the frontend's typewriter handles
smooth reveal, and Claude vision over Emergent proxy works most reliably non-streamed.
"""
import base64
import re
import uuid
from typing import Iterable, Tuple

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

from app.config import get_settings

settings = get_settings()

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

_DATA_URL_RE = re.compile(r"^data:([\w./+-]+);base64,(.+)$", re.DOTALL)


def parse_data_urls(images: Iterable[str]) -> list[Tuple[str, str]]:
    """
    Validate + decode a list of data URLs.
    Returns a list of (mime_type, raw_base64) tuples. Raises ValueError on invalid input.
    """
    out: list[Tuple[str, str]] = []
    for raw in images or []:
        m = _DATA_URL_RE.match(raw or "")
        if not m:
            raise ValueError("Image must be a base64 data URL (data:image/...;base64,...)")
        mime, b64 = m.group(1).lower(), m.group(2)
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in ALLOWED_MIME:
            raise ValueError(f"Unsupported image type {mime!r} — use JPEG, PNG or WEBP")
        try:
            decoded = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise ValueError(f"Invalid base64 image payload: {e}")
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ValueError(f"Image too large ({len(decoded) // 1024} KB) — max 5 MB per image")
        if len(decoded) < 128:
            raise ValueError("Image payload is too small to be valid")
        out.append((mime, b64))
    return out


async def claude_vision_answer(
    *,
    system_prompt: str,
    user_text: str,
    images_b64: list[Tuple[str, str]],
    session_id: str | None = None,
) -> str:
    """
    Call Claude Sonnet 4.6 with text + image attachments via Emergent proxy.
    Returns the assistant's text answer.
    """
    chat = LlmChat(
        api_key=settings.emergent_llm_key,
        session_id=session_id or str(uuid.uuid4()),
        system_message=system_prompt,
    ).with_model("anthropic", "claude-sonnet-4-6")

    file_contents = [ImageContent(image_base64=b64) for (_mime, b64) in images_b64]

    response = await chat.send_message(UserMessage(
        text=user_text,
        file_contents=file_contents,
    ))
    if isinstance(response, str):
        return response
    # LlmChat returns plain string per playbook
    return str(response)
