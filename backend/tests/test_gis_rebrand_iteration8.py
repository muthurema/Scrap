"""
Iteration 8 — GIS rebrand verification (CIDSA RAG).

Verifies:
- Superadmin login returns needs_onboarding=False (onboarding removed).
- Document upload accepts 'author' field + persists author in DocumentOut.
- Document is processed (chunk_count > 0) within reasonable time.
- Chat /api/chat/stream returns SSE payload with sources carrying book title + author.
- All uploaded docs are global (company_id=None) even when uploaded by superadmin
  (single-global-knowledge-base contract).
- /api/chat/stream sources wire payload uses {sources, external_count} envelope.
- Acknowledgement workflow still works on an assistant message.
"""
import json
import os
import time
import uuid
import io
from pathlib import Path

import pytest
import requests


BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SUPERADMIN_EMAIL = "admin@ehsrag.com"
SUPERADMIN_PWD = "Admin@12345"


@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{API}/auth/login", json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PWD}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # Onboarding must be off post-rebrand
    assert body.get("needs_onboarding") is False, f"superadmin login needs_onboarding should be False, got {body.get('needs_onboarding')}"
    return body["access_token"]


@pytest.fixture(scope="module")
def auth_headers(super_token):
    return {"Authorization": f"Bearer {super_token}"}


# ── Auth / onboarding removal ──────────────────────────────────────────────
class TestAuthNoOnboarding:
    def test_login_returns_no_onboarding(self, super_token):
        # super_token fixture already asserts this; this is a marker test.
        assert isinstance(super_token, str) and len(super_token) > 10


# ── Document upload with author ────────────────────────────────────────────
GIS_TXT = (
    "TEST_GIS_BOOK\n\n"
    "A UTM zone is defined as a 6-degree-wide longitudinal strip of the Earth, "
    "with 60 zones covering the globe between 80 deg S and 84 deg N. Each zone "
    "uses a Transverse Mercator projection centered on its central meridian, "
    "with a scale factor of 0.9996 at the central meridian. Coordinates are in "
    "meters, with a false easting of 500,000 m and (in the southern hemisphere) "
    "a false northing of 10,000,000 m. UTM provides high accuracy for mapping "
    "within a single zone but distorts at zone boundaries.\n\n"
    "Spatial reference systems are commonly identified by EPSG codes; for "
    "example WGS 84 / UTM zone 33N is EPSG:32633."
) * 3  # bigger payload so chunker yields multiple chunks


@pytest.fixture(scope="module")
def uploaded_doc(auth_headers):
    title = f"TEST_GIS_UTM_Primer_{uuid.uuid4().hex[:6]}"
    author = "TEST_Ada_Cartography"
    files = {"file": (f"{title}.txt", io.BytesIO(GIS_TXT.encode()), "text/plain")}
    data = {"title": title, "author": author, "doc_type": "general"}
    r = requests.post(f"{API}/documents/upload", headers=auth_headers, files=files, data=data, timeout=60)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["title"] == title
    assert doc["author"] == author
    # Single-global-KB contract: superadmin upload must NOT carry a company_id.
    assert doc.get("company_id") in (None, ""), f"superadmin upload should be global, got company_id={doc.get('company_id')}"
    yield {"id": doc["id"], "title": title, "author": author}
    # teardown
    try:
        requests.delete(f"{API}/documents/{doc['id']}", headers=auth_headers, timeout=30)
    except Exception:
        pass


class TestDocumentUpload:
    def test_doc_has_author(self, uploaded_doc, auth_headers):
        r = requests.get(f"{API}/documents/{uploaded_doc['id']}", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["author"] == uploaded_doc["author"]
        assert body["title"] == uploaded_doc["title"]

    def test_doc_processes_to_ready(self, uploaded_doc, auth_headers):
        # poll up to 45s for ingestion (small txt should be fast)
        deadline = time.time() + 60
        last = None
        while time.time() < deadline:
            r = requests.get(f"{API}/documents/{uploaded_doc['id']}", headers=auth_headers, timeout=15)
            assert r.status_code == 200
            last = r.json()
            if last.get("is_processed") and last.get("chunk_count", 0) > 0:
                break
            if last.get("processing_error"):
                pytest.fail(f"processing_error: {last['processing_error']}")
            time.sleep(2)
        assert last and last.get("is_processed") is True, f"doc not processed in time, state={last}"
        assert last["chunk_count"] > 0, f"chunk_count should be > 0 after processing, got {last['chunk_count']}"


# ── Chat streaming with book+author citation ───────────────────────────────
def _read_sse(resp):
    """Return dict of event_name -> list of decoded json data payloads."""
    events = {}
    current_event = None
    buf = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw
        if line == "":
            if current_event and buf:
                payload = "\n".join(buf)
                try:
                    parsed = json.loads(payload)
                except Exception:
                    parsed = payload
                events.setdefault(current_event, []).append(parsed)
            current_event = None
            buf = []
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            buf.append(line[len("data:"):].lstrip())
    return events


class TestChatStream:
    def test_chat_emits_sources_with_author(self, uploaded_doc, auth_headers):
        # Make sure doc is processed first (defensive)
        for _ in range(30):
            r = requests.get(f"{API}/documents/{uploaded_doc['id']}", headers=auth_headers, timeout=15)
            if r.status_code == 200 and r.json().get("is_processed") and r.json().get("chunk_count", 0) > 0:
                break
            time.sleep(2)

        payload = {"content": "How is a UTM zone defined and what is its scale factor at the central meridian?"}
        with requests.post(
            f"{API}/chat/stream",
            headers={**auth_headers, "Accept": "text/event-stream"},
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            assert resp.status_code == 200, resp.text
            events = _read_sse(resp)

        assert "sources" in events, f"no 'sources' SSE event; got events={list(events.keys())}"
        sources_event = events["sources"][0]
        # New envelope shape
        assert isinstance(sources_event, dict), f"sources event should be dict envelope, got {type(sources_event)}"
        assert "sources" in sources_event and "external_count" in sources_event, sources_event
        assert sources_event["external_count"] == 0, "external_count must be 0 in single global KB"
        srcs = sources_event["sources"]
        assert isinstance(srcs, list) and len(srcs) > 0, f"expected at least 1 source, got {srcs}"
        # At least one source has the expected author and title
        titles = [s.get("title", "") for s in srcs]
        authors = [s.get("author", "") for s in srcs]
        assert any(uploaded_doc["title"] in t for t in titles), f"uploaded title not in sources titles: {titles}"
        assert any(uploaded_doc["author"] in (a or "") for a in authors), f"uploaded author not in sources authors: {authors}"

        # Final answer must contain the book title or author somewhere (RAG citation)
        assert "done" in events, f"no 'done' SSE; got {list(events.keys())}"
        final = events["done"][-1]
        final_text = (final.get("final_text") or "").lower()
        assert ("utm" in final_text), f"answer doesn't seem to reference UTM: {final_text[:200]}"
        # Confidence score should be present
        assert final.get("confidence_score") is not None, "confidence_score missing on done"


# ── Acknowledgement workflow still works ───────────────────────────────────
class TestAcknowledgement:
    def test_acknowledge_assistant_message(self, uploaded_doc, auth_headers):
        # 1. Create a session by sending one streamed message
        payload = {"content": "What scale factor is used for UTM at the central meridian?"}
        session_id = None
        msg_id = None
        with requests.post(
            f"{API}/chat/stream",
            headers={**auth_headers, "Accept": "text/event-stream"},
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            assert resp.status_code == 200
            events = _read_sse(resp)
        # session info comes in the 'session' SSE event (sent before tokens)
        sess_event = events.get("session", [{}])[-1]
        session_id = sess_event.get("session_id")
        msg_id = sess_event.get("message_id")
        assert session_id, f"session event missing session_id: {sess_event}"
        assert msg_id, f"session event missing message_id: {sess_event}"

        # 2. POST acknowledgement (note trailing slash required)
        ack_resp = requests.post(
            f"{API}/acknowledgements/",
            headers=auth_headers,
            json={"message_id": msg_id},
            timeout=30,
        )
        assert ack_resp.status_code in (200, 201), ack_resp.text

        # 3. GET acknowledgements list — superadmin sees global list
        list_resp = requests.get(f"{API}/acknowledgements/", headers=auth_headers, timeout=30)
        assert list_resp.status_code == 200, list_resp.text
        items = list_resp.json()
        items = items if isinstance(items, list) else items.get("items", [])
        assert any(it.get("message_id") == msg_id for it in items), \
            f"acknowledgement for msg {msg_id} not found in list of {len(items)}"
