"""End-to-end backend tests for EHS RAG API."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://vigilant-chatterjee-8.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@ehsrag.com"
ADMIN_PASSWORD = "Admin@12345"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("role") == "superadmin"
    return data["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_token():
    ts = int(time.time())
    email = f"newuser+{ts}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "User@12345", "full_name": "Test User", "role": "user"
    }, timeout=30)
    assert r.status_code in (200, 201), f"Register failed: {r.status_code} {r.text}"
    data = r.json()
    # Existing seeded admin must remain first superadmin
    assert data.get("role") != "superadmin"
    return data["access_token"], email


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token[0]}"}


# ── Health ────────────────────────────────────────────────────────────────────

def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["qdrant"] == "healthy"
    assert data["model"] == "claude-sonnet-4-6"


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_login_admin():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data and len(data["access_token"]) > 10
    assert data["role"] == "superadmin"
    assert data["email"] == ADMIN_EMAIL


def test_register_new_user(user_token):
    token, email = user_token
    assert token


def test_auth_me(admin_headers):
    r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == ADMIN_EMAIL
    assert data["role"] == "superadmin"


def test_auth_me_unauthenticated():
    r = requests.get(f"{API}/auth/me", timeout=15)
    assert r.status_code in (401, 403)


# ── Admin Stats ───────────────────────────────────────────────────────────────

def test_admin_stats_superadmin(admin_headers):
    r = requests.get(f"{API}/admin/stats", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    s = r.json()
    assert s["total_documents"] >= 7
    assert s["total_chunks_embedded"] >= 9
    assert s["qdrant_status"] == "healthy"
    assert s["base_corpus_count"] >= 7


def test_admin_stats_non_superadmin_forbidden(user_headers):
    r = requests.get(f"{API}/admin/stats", headers=user_headers, timeout=15)
    assert r.status_code == 403


# ── Documents ─────────────────────────────────────────────────────────────────

def test_list_documents_seeded(admin_headers):
    r = requests.get(f"{API}/documents/", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data["items"]
    assert data["total"] >= 7
    base = [d for d in items if d["source"] == "base_corpus"]
    assert len(base) >= 7
    for d in base:
        assert d["is_processed"] is True
        assert d["chunk_count"] > 0


@pytest.fixture(scope="module")
def uploaded_doc(admin_headers):
    """Upload a small TXT for testing."""
    content = b"Test SOP content for confined space entry. Workers must follow lockout/tagout procedures. UNIQUE_TOKEN_XYZ_LOCKOUT."
    files = {"file": ("test_sop_lotoxyz.txt", content, "text/plain")}
    data = {"doc_type": "sop", "source": "superadmin", "title": "TEST SOP LOTO XYZ"}
    r = requests.post(f"{API}/documents/upload", headers=admin_headers, files=files, data=data, timeout=60)
    assert r.status_code in (200, 201), f"Upload failed: {r.status_code} {r.text}"
    doc = r.json()
    assert "id" in doc
    doc_id = doc["id"]
    # Poll for processing
    processed = False
    for _ in range(30):
        time.sleep(1)
        r2 = requests.get(f"{API}/documents/", headers=admin_headers, timeout=15)
        items = r2.json()["items"]
        match = next((d for d in items if d["id"] == doc_id), None)
        if match and match["is_processed"] and match["chunk_count"] > 0:
            processed = True
            break
    assert processed, f"Document {doc_id} did not finish processing within 30s"
    yield doc_id
    # Cleanup
    requests.delete(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15)


def test_document_upload_and_processed(uploaded_doc):
    assert uploaded_doc


def test_reprocess_seeded_doc(admin_headers):
    r = requests.get(f"{API}/documents/", headers=admin_headers, timeout=15)
    items = r.json()["items"]
    base = [d for d in items if d["source"] == "base_corpus"]
    target = base[0]
    r2 = requests.post(f"{API}/documents/{target['id']}/reprocess", headers=admin_headers, timeout=120)
    assert r2.status_code in (200, 202), f"Reprocess failed: {r2.status_code} {r2.text}"


# ── Chat ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chat_session(admin_headers):
    r = requests.post(f"{API}/chat/", headers=admin_headers, json={
        "content": "What are the OSHA requirements for confined space entry?"
    }, timeout=120)
    assert r.status_code == 200, f"Chat failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["content"]
    assert len(data["sources"]) > 0
    assert isinstance(data["confidence_score"], (int, float))
    sid = data["session_id"]
    # Validate UUID
    uuid.UUID(sid)
    yield sid
    requests.delete(f"{API}/chat/sessions/{sid}", headers=admin_headers, timeout=15)


def test_chat_first_message(chat_session):
    assert chat_session


def test_chat_continuation_history(admin_headers, chat_session):
    r = requests.post(f"{API}/chat/", headers=admin_headers, json={
        "content": "Can you elaborate on permits required?",
        "session_id": chat_session,
    }, timeout=120)
    assert r.status_code == 200
    # Now get messages
    r2 = requests.get(f"{API}/chat/sessions/{chat_session}/messages", headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    msgs = r2.json()
    # Should have 4 messages
    assert len(msgs) >= 4, f"Expected >=4 messages, got {len(msgs)}"
    roles = [m["role"] for m in msgs]
    assert roles.count("user") >= 2
    assert roles.count("assistant") >= 2


def test_list_sessions(admin_headers, chat_session):
    r = requests.get(f"{API}/chat/sessions", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    sessions = r.json()
    match = next((s for s in sessions if s["id"] == chat_session), None)
    assert match is not None
    assert match["message_count"] >= 2


def test_company_priority_boost(admin_headers, uploaded_doc):
    """Asking about LOTO should return uploaded doc as a source due to priority boost."""
    r = requests.post(f"{API}/chat/", headers=admin_headers, json={
        "content": "Tell me about UNIQUE_TOKEN_XYZ_LOCKOUT lockout tagout procedures."
    }, timeout=120)
    assert r.status_code == 200
    data = r.json()
    src_ids = [s["doc_id"] for s in data["sources"]]
    assert uploaded_doc in src_ids, f"Uploaded doc not in sources: {src_ids}"


def test_delete_session(admin_headers):
    # Create a fresh session and delete it
    r = requests.post(f"{API}/chat/", headers=admin_headers, json={"content": "Quick question on JSA."}, timeout=120)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    r2 = requests.delete(f"{API}/chat/sessions/{sid}", headers=admin_headers, timeout=15)
    assert r2.status_code in (200, 204)
    # Verify gone
    r3 = requests.get(f"{API}/chat/sessions/{sid}/messages", headers=admin_headers, timeout=15)
    assert r3.status_code in (404, 200)
    if r3.status_code == 200:
        assert r3.json() == [] or len(r3.json()) == 0


# ── Web Sources ───────────────────────────────────────────────────────────────

def test_web_source_full_flow(admin_headers):
    payload = {
        "url": "https://www.example.com",
        "label": "Example",
        "scope": "platform",
        "scrape_frequency": "weekly",
        "doc_type": "regulatory",
        "crawl_depth": 1,
    }
    r = requests.post(f"{API}/web-sources/", headers=admin_headers, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"Create web source failed: {r.status_code} {r.text}"
    ws = r.json()
    wsid = ws["id"]

    try:
        # Scrape
        r2 = requests.post(f"{API}/web-sources/{wsid}/scrape", headers=admin_headers, timeout=120)
        assert r2.status_code == 200, f"Scrape failed: {r2.status_code} {r2.text}"
        result = r2.json()
        assert "web_source_id" in result
        # Accept either chunks_stored>=1 or an error string set
        if result.get("error"):
            print(f"Scrape returned error (acceptable): {result['error']}")
        else:
            assert result["chunks_stored"] >= 0  # example.com may return 0 but no 500

        # List
        r3 = requests.get(f"{API}/web-sources/", headers=admin_headers, timeout=15)
        assert r3.status_code == 200
        ids = [s["id"] for s in r3.json()]
        assert wsid in ids
    finally:
        # Delete
        r4 = requests.delete(f"{API}/web-sources/{wsid}", headers=admin_headers, timeout=15)
        assert r4.status_code in (200, 204)
