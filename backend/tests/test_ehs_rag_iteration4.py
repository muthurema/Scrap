"""
Iteration 4 backend tests — P0 event loop responsiveness during document ingestion,
async password hashing, split health endpoints, vector batch upsert, doc upload/cancel/delete,
and chat streaming regression.

Single-worker uvicorn is intentional (fastembed + qdrant local-file mode aren't fork-safe).
"""
import os
import time
import uuid
import threading
import statistics
import pytest
import requests

# Read REACT_APP_BACKEND_URL from frontend/.env
_env_url = os.environ.get("REACT_APP_BACKEND_URL")
if not _env_url:
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    _env_url = _line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
assert _env_url, "REACT_APP_BACKEND_URL not configured"
BASE_URL = _env_url.rstrip("/")

ADMIN_EMAIL = "admin@ehsrag.com"
ADMIN_PASS = "Admin@12345"


# ──────────────── Fixtures ────────────────

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("role") == "superadmin"
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ──────────────── Health endpoint split ────────────────

def test_health_no_qdrant_field():
    """/api/health must NOT touch qdrant (no qdrant field)."""
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"
    assert data.get("models_ready") is True
    assert "qdrant" not in data, "qdrant field should be moved to /api/health/qdrant"


def test_health_qdrant_split():
    r = requests.get(f"{BASE_URL}/api/health/qdrant", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("qdrant") == "healthy"


def test_health_fast_under_load():
    """Baseline: /api/health should respond well under 2s even with no concurrent ingestion."""
    durations = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        durations.append(time.perf_counter() - t0)
        assert r.status_code == 200
    assert max(durations) < 2.0, f"health endpoint slow: {durations}"


# ──────────────── Auth async wrappers ────────────────

def test_login_async_verify_password(admin_token):
    """Login must work with new verify_password_async."""
    assert admin_token and len(admin_token) > 20


def test_login_wrong_password():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": "WrongPass@123"}, timeout=10)
    assert r.status_code in (400, 401)


def test_register_already_registered_email():
    """Re-registering admin email should fail (already exists)."""
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": ADMIN_EMAIL, "password": "anything", "full_name": "Dup"},
                      timeout=15)
    # Backend should reject duplicate emails (any 4xx)
    assert r.status_code in (400, 409, 422), r.text


def test_register_invite_only_gating():
    """Registration should be invite-only — random emails get 403 gating message."""
    email = f"iter4_async_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": email, "password": "TestPass@123", "full_name": "Async Hash"},
                      timeout=30)
    # Invite-only signup gating must reject random emails
    assert r.status_code == 403, r.text
    assert "invitation" in r.text.lower() or "invite" in r.text.lower() or "allowlist" in r.text.lower()


def test_register_with_invite_code_uses_async_hash(admin_headers):
    """Generate an invite code as admin, register with it — exercises hash_password_async."""
    # Try to create an invite. Endpoint may vary; try common paths.
    invite_email = f"iter4_invited_{uuid.uuid4().hex[:6]}@example.com"
    code = None
    for path, payload in (
        ("/api/invites/", {"email": invite_email, "role": "user"}),
        ("/api/invites", {"email": invite_email, "role": "user"}),
        ("/api/auth/invites/", {"email": invite_email, "role": "user"}),
    ):
        try:
            cr = requests.post(f"{BASE_URL}{path}", headers=admin_headers,
                               json=payload, timeout=10)
            if cr.status_code in (200, 201):
                body = cr.json()
                code = body.get("code") or body.get("invite_code") or body.get("token")
                if code:
                    break
        except Exception:
            continue
    if not code:
        pytest.skip("Could not create invite code via known endpoints; gating itself verified above")
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": invite_email, "password": "TestPass@123",
                            "full_name": "Invited", "invite_code": code},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    assert "access_token" in r.json()
    # Verify password verify_password_async path on login
    r2 = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": invite_email, "password": "TestPass@123"}, timeout=15)
    assert r2.status_code == 200, r2.text


# ──────────────── Document upload + processing ────────────────

def _upload_txt(headers, content_bytes, title, **form):
    files = {"file": (f"{title}.txt", content_bytes, "text/plain")}
    data = {"title": title, "doc_type": "policy", "source": "superadmin", **form}
    return requests.post(f"{BASE_URL}/api/documents/upload",
                         headers=headers, files=files, data=data, timeout=60)


def _wait_processed(admin_headers, doc_id, timeout_s=90):
    start = time.time()
    while time.time() - start < timeout_s:
        chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                           headers=admin_headers, timeout=15).json()
        item = next((d for d in chk["items"] if d["id"] == doc_id), None)
        if item and item.get("is_processed"):
            return item
        if item and item.get("processing_error"):
            return item
        time.sleep(1)
    return None


def test_upload_small_doc_and_processed(admin_headers):
    body = b"ITER4 small doc - LOTO procedure overview content. " * 8
    r = _upload_txt(admin_headers, body, f"iter4_small_{uuid.uuid4().hex[:6]}")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc.get("id")
    assert doc.get("is_processed") in (False, None)  # async background
    processed = _wait_processed(admin_headers, doc["id"], timeout_s=60)
    assert processed is not None, "Doc never processed"
    assert processed.get("is_processed") is True
    assert processed.get("chunk_count", 0) > 0
    assert not processed.get("processing_error")
    # Cleanup
    requests.delete(f"{BASE_URL}/api/documents/{doc['id']}", headers=admin_headers, timeout=15)


def test_cancel_doc_during_processing(admin_headers):
    """Upload a doc and immediately cancel — file should be removed and 200 returned."""
    body = b"ITER4 cancel test content " * 200
    r = _upload_txt(admin_headers, body, f"iter4_cancel_{uuid.uuid4().hex[:6]}")
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    # Cancel immediately
    cr = requests.post(f"{BASE_URL}/api/documents/{doc_id}/cancel",
                       headers=admin_headers, timeout=15)
    assert cr.status_code == 200, cr.text
    # After cancel doc should be gone (or marked deleted)
    time.sleep(2)
    chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                       headers=admin_headers, timeout=15).json()
    ids = {d["id"] for d in chk["items"]}
    assert doc_id not in ids, "Cancelled doc still present in listing"


def test_delete_doc_returns_204(admin_headers):
    body = b"ITER4 delete test " * 20
    r = _upload_txt(admin_headers, body, f"iter4_delete_{uuid.uuid4().hex[:6]}")
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    # Wait for processing so chunks exist to clean up
    _wait_processed(admin_headers, doc_id, timeout_s=60)
    dr = requests.delete(f"{BASE_URL}/api/documents/{doc_id}",
                         headers=admin_headers, timeout=15)
    assert dr.status_code == 204, dr.text
    # Verify gone
    chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                       headers=admin_headers, timeout=15).json()
    assert doc_id not in {d["id"] for d in chk["items"]}


# ──────────────── Batch vector upsert (100+ chunks) ────────────────

def test_large_doc_all_chunks_indexed(admin_headers):
    """Upload a doc large enough to produce 100+ chunks (varied content to avoid dedup).
    Verifies new BATCH=64 vector_store path can ingest >1 batch."""
    # Build varied content: each section has a unique numeric token so chunks don't dedup.
    sections = []
    base = (
        "Lockout tagout LOTO procedures require isolation of all hazardous energy sources "
        "before any maintenance activity. Personal protective equipment PPE includes hard hat, "
        "safety glasses, gloves, steel-toe boots, hearing protection. Confined space entry needs "
        "atmospheric monitoring for oxygen, LEL, hydrogen sulfide, carbon monoxide. Hot work "
        "permits cover welding, cutting, grinding within 35 feet of flammables. Job safety "
        "analysis JSA identifies hazards step by step. Emergency response includes muster points, "
        "evacuation routes, accountability rosters. Chemical hazard communication relies on SDS "
        "review and proper labeling. Fall protection above six feet requires harness and lanyard."
    )
    for i in range(400):
        sections.append(f"Section {i}: unique_token_{uuid.uuid4().hex[:8]} {base}")
    body = ("\n\n".join(sections)).encode("utf-8")
    r = _upload_txt(admin_headers, body, f"iter4_large_{uuid.uuid4().hex[:6]}")
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    processed = _wait_processed(admin_headers, doc_id, timeout_s=240)
    assert processed is not None, "Large doc never processed"
    assert processed.get("is_processed") is True, f"not processed: {processed}"
    assert not processed.get("processing_error"), f"processing_error: {processed.get('processing_error')}"
    chunk_count = processed.get("chunk_count", 0)
    print(f"\nLarge doc chunk_count={chunk_count}")
    assert chunk_count >= 100, f"Expected 100+ chunks (to exercise BATCH=64 path), got {chunk_count}"
    # Cleanup
    requests.delete(f"{BASE_URL}/api/documents/{doc_id}", headers=admin_headers, timeout=15)


# ──────────────── P0: Event loop responsiveness during ingestion ────────────────

def test_event_loop_responsive_during_ingestion(admin_headers):
    """
    P0 test: while a large doc is being ingested in the background, concurrently hit
    /api/health and /api/auth/login. Both must respond well within 2s window.
    """
    # Start a large ingestion in background thread (don't block)
    paragraph = (
        "Concurrency test paragraph for ingestion responsiveness. LOTO procedure, "
        "confined space, PPE, JSA, SDS, hot work permit, fall protection. " * 4
    )
    body = (paragraph * 250).encode("utf-8")

    upload_resp = {}
    def do_upload():
        r = _upload_txt(admin_headers, body, f"iter4_p0_{uuid.uuid4().hex[:6]}")
        upload_resp["r"] = r

    t = threading.Thread(target=do_upload, daemon=True)
    t.start()

    # Wait briefly so the upload starts and background ingestion begins
    time.sleep(2.0)

    # Now hammer /api/health and /api/auth/login in main thread while ingestion runs.
    health_durations = []
    login_durations = []
    login_errors = 0
    health_errors = 0

    iterations = 10
    for _ in range(iterations):
        # Health
        t0 = time.perf_counter()
        try:
            hr = requests.get(f"{BASE_URL}/api/health", timeout=5)
            health_durations.append(time.perf_counter() - t0)
            if hr.status_code != 200:
                health_errors += 1
        except Exception:
            health_errors += 1
            health_durations.append(5.0)

        # Login
        t0 = time.perf_counter()
        try:
            lr = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=5)
            login_durations.append(time.perf_counter() - t0)
            if lr.status_code != 200:
                login_errors += 1
        except Exception:
            login_errors += 1
            login_durations.append(5.0)

        time.sleep(0.3)

    # Wait for upload thread to finish to clean up
    t.join(timeout=120)

    print(f"\nHealth: median={statistics.median(health_durations):.3f}s "
          f"max={max(health_durations):.3f}s errors={health_errors}")
    print(f"Login:  median={statistics.median(login_durations):.3f}s "
          f"max={max(login_durations):.3f}s errors={login_errors}")

    # Cleanup if upload succeeded
    if upload_resp.get("r") is not None and upload_resp["r"].status_code == 201:
        try:
            doc_id = upload_resp["r"].json()["id"]
            # Wait for processing to finish or just delete
            _wait_processed(admin_headers, doc_id, timeout_s=120)
            requests.delete(f"{BASE_URL}/api/documents/{doc_id}",
                            headers=admin_headers, timeout=15)
        except Exception:
            pass

    # Assertions: no errors, all responses < 2s (per problem statement)
    assert health_errors == 0, f"health errors during ingestion: {health_errors}"
    assert login_errors == 0, f"login errors during ingestion: {login_errors}"
    assert max(health_durations) < 2.0, \
        f"health endpoint exceeded 2s during ingestion. max={max(health_durations):.3f}s"
    assert max(login_durations) < 2.0, \
        f"login endpoint exceeded 2s during ingestion. max={max(login_durations):.3f}s"


# ──────────────── Chat streaming regression ────────────────

def test_chat_stream_basic(admin_headers):
    payload = {"content": "What is JSA in 1 sentence?"}
    with requests.post(f"{BASE_URL}/api/chat/stream", headers=admin_headers,
                       json=payload, stream=True, timeout=120) as r:
        assert r.status_code == 200
        got_token = False
        got_done = False
        current_event = None
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("event:"):
                current_event = raw.split(":", 1)[1].strip()
            elif raw.startswith("data:"):
                if current_event == "token":
                    got_token = True
                elif current_event == "done":
                    got_done = True
                    break
        assert got_token, "no token events streamed"
        assert got_done, "no done event received"
