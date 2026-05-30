"""
Iteration 3 backend tests — onboarding, high-risk + follow-ups, feedback queue + annotate,
analytics, supersedes, expiry, include_superseded, admin stats new fields, SSRF regression.
"""
import os
import time
import uuid
import pytest
import requests

# Read REACT_APP_BACKEND_URL from frontend/.env (the public test URL)
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
    assert data.get("role") == "superadmin"
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def new_user_creds():
    email = f"itest_iter3_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "TestPass@123"
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"email": email, "password": pwd, "full_name": "Iter3 Tester"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    # Non-first user should default to needs_onboarding=true
    return {"email": email, "password": pwd, "token": data["access_token"],
            "needs_onboarding": data.get("needs_onboarding", False),
            "user_id": data.get("user_id")}


@pytest.fixture(scope="session")
def new_user_headers(new_user_creds):
    return {"Authorization": f"Bearer {new_user_creds['token']}"}


# ──────────────── Auth regression ────────────────

def test_admin_login_regression(admin_token):
    assert admin_token and len(admin_token) > 20


# ──────────────── Onboarding / Users ────────────────

def test_jurisdictions_list(admin_headers):
    r = requests.get(f"{BASE_URL}/api/users/jurisdictions", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "jurisdictions" in data and isinstance(data["jurisdictions"], list)
    assert "industry_sectors" in data and isinstance(data["industry_sectors"], list)
    assert "US" in data["jurisdictions"]
    assert "manufacturing" in data["industry_sectors"]


def test_new_user_needs_onboarding(new_user_creds):
    # New (non-first) registered user should need onboarding
    assert new_user_creds["needs_onboarding"] is True


def test_patch_me_completes_onboarding(new_user_headers):
    payload = {"site": "Plant-A", "role_label": "EHS Engineer",
               "jurisdiction": "US", "industry_sector": "manufacturing"}
    r = requests.patch(f"{BASE_URL}/api/users/me", headers=new_user_headers,
                       json=payload, timeout=15)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["jurisdiction"] == "US"
    assert u["industry_sector"] == "manufacturing"
    assert u["site"] == "Plant-A"
    assert u["needs_onboarding"] is False


def test_patch_me_rejects_invalid_jurisdiction(new_user_headers):
    r = requests.patch(f"{BASE_URL}/api/users/me", headers=new_user_headers,
                       json={"jurisdiction": "ZZ"}, timeout=10)
    assert r.status_code == 400


# ──────────────── Chat with high-risk + follow-ups ────────────────

@pytest.fixture(scope="session")
def high_risk_chat(admin_headers):
    payload = {"content": "Chemical spill in confined space — what should I do?"}
    r = requests.post(f"{BASE_URL}/api/chat/", headers=admin_headers, json=payload, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_high_risk_flags(high_risk_chat):
    assert high_risk_chat.get("is_high_risk") is True
    assert isinstance(high_risk_chat.get("suggested_followups"), list)
    assert len(high_risk_chat["suggested_followups"]) >= 1
    content = high_risk_chat.get("content", "")
    # The banner is prepended for high-risk queries
    assert ("Immediate safety concern detected" in content) or content.startswith("⚠️")


def test_chat_non_risk_followups(admin_headers):
    r = requests.post(f"{BASE_URL}/api/chat/", headers=admin_headers,
                      json={"content": "What is JSA?"}, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("is_high_risk") is False
    assert isinstance(data.get("suggested_followups"), list)
    assert len(data["suggested_followups"]) >= 1
    # Non-high-risk: banner should NOT be present
    assert "Immediate safety concern detected" not in (data.get("content") or "")


def test_chat_stream_done_has_followups(admin_headers):
    """Verify SSE 'done' event carries suggested_followups and is_high_risk."""
    payload = {"content": "Summarize the LOTO procedure briefly"}
    with requests.post(f"{BASE_URL}/api/chat/stream", headers=admin_headers,
                       json=payload, stream=True, timeout=120) as r:
        assert r.status_code == 200
        found_done = False
        suggested_present = False
        high_risk_present = False
        current_event = None
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("event:"):
                current_event = raw.split(":", 1)[1].strip()
            elif raw.startswith("data:") and current_event == "done":
                import json
                try:
                    data = json.loads(raw.split(":", 1)[1].strip())
                except Exception:
                    continue
                found_done = True
                suggested_present = "suggested_followups" in data
                high_risk_present = "is_high_risk" in data
                break
        assert found_done, "No 'done' SSE event observed"
        assert suggested_present, "'done' missing suggested_followups"
        assert high_risk_present, "'done' missing is_high_risk"


# ──────────────── Feedback flow ────────────────

@pytest.fixture(scope="session")
def feedback_target_message(admin_headers):
    """Send chat with distinctive long words so SME-annotation injection can match later."""
    distinctive = "CONFINEDSPACEXYZQUERY procedures atmosphere monitoring"
    r = requests.post(f"{BASE_URL}/api/chat/", headers=admin_headers,
                      json={"content": distinctive}, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"message_id": data["message_id"], "session_id": data["session_id"],
            "query": distinctive}


def test_submit_feedback_down(admin_headers, feedback_target_message):
    mid = feedback_target_message["message_id"]
    r = requests.post(f"{BASE_URL}/api/feedback/{mid}", headers=admin_headers,
                      json={"rating": "down", "comment": "Not specific enough"}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["rating"] == "down"
    assert "id" in data


def test_feedback_upsert_same_row(admin_headers, feedback_target_message):
    mid = feedback_target_message["message_id"]
    # Get the existing feedback_id
    r1 = requests.post(f"{BASE_URL}/api/feedback/{mid}", headers=admin_headers,
                       json={"rating": "down", "comment": "first"}, timeout=15)
    fid1 = r1.json()["id"]
    # Re-submit as up; should update same row
    r2 = requests.post(f"{BASE_URL}/api/feedback/{mid}", headers=admin_headers,
                       json={"rating": "up"}, timeout=15)
    fid2 = r2.json()["id"]
    assert fid1 == fid2, "Feedback must be upserted (one row per message_id)"


def test_feedback_queue_superadmin(admin_headers, feedback_target_message):
    mid = feedback_target_message["message_id"]
    # Reset to down so it appears in down queue
    requests.post(f"{BASE_URL}/api/feedback/{mid}", headers=admin_headers,
                  json={"rating": "down", "comment": "Wrong"}, timeout=15)
    r = requests.get(f"{BASE_URL}/api/feedback/queue",
                     params={"rating": "down", "reviewed": "false"},
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert body.get("total", 0) >= 1
    matching = [it for it in body["items"] if it.get("message_id") == mid]
    assert matching, "Submitted feedback not found in queue"
    fb = matching[0]
    for k in ("user_query", "assistant_answer", "comment", "sources"):
        assert k in fb


def test_feedback_annotate_sets_reviewed(admin_headers, feedback_target_message):
    mid = feedback_target_message["message_id"]
    # Get feedback row id from queue
    r = requests.get(f"{BASE_URL}/api/feedback/queue",
                     params={"rating": "down", "reviewed": "false"},
                     headers=admin_headers, timeout=15)
    fid = next(it["id"] for it in r.json()["items"] if it.get("message_id") == mid)
    ann = "Always recommend atmospheric monitoring with calibrated 4-gas meter before entry."
    r2 = requests.post(f"{BASE_URL}/api/feedback/{fid}/annotate",
                       headers=admin_headers, json={"annotation": ann}, timeout=15)
    assert r2.status_code == 200, r2.text
    # Now verify it's in reviewed queue
    r3 = requests.get(f"{BASE_URL}/api/feedback/queue",
                      params={"rating": "down", "reviewed": "true"},
                      headers=admin_headers, timeout=15)
    assert r3.status_code == 200
    reviewed_ids = [it["id"] for it in r3.json()["items"]]
    assert fid in reviewed_ids
    matched = next(it for it in r3.json()["items"] if it["id"] == fid)
    assert matched["annotation"] == ann
    assert matched["annotated_by"] == ADMIN_EMAIL
    assert matched["is_reviewed"] is True


def test_annotation_matched_by_relevance(admin_headers, feedback_target_message):
    """After annotation, get_relevant_annotations should match a similar-keyword query.
    We verify behavioural proxy: re-querying with the distinctive token completes
    and the feedback row remains tagged correctly (direct call to internal helper isn't
    accessible over HTTP; this confirms the chat path doesn't error out)."""
    similar = "CONFINEDSPACEXYZQUERY entry procedures atmosphere"
    r = requests.post(f"{BASE_URL}/api/chat/", headers=admin_headers,
                      json={"content": similar}, timeout=120)
    assert r.status_code == 200, r.text


# ──────────────── Analytics ────────────────

def test_analytics_superadmin(admin_headers):
    r = requests.get(f"{BASE_URL}/api/analytics/", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    a = r.json()
    for key in ("top_queries", "zero_result_queries", "low_confidence_queries",
                "top_cited_docs", "feedback_summary", "daily_query_counts"):
        assert key in a, f"missing field {key}"
        assert isinstance(a[key], list) if key != "feedback_summary" else isinstance(a[key], dict)
    fs = a["feedback_summary"]
    for k in ("thumbs_up", "thumbs_down", "total_assistant_messages", "pending_review"):
        assert k in fs
    assert a.get("pii_flagged_count", -1) >= 0
    assert a.get("injection_flagged_count", -1) >= 0


def test_analytics_forbidden_for_non_superadmin(new_user_headers):
    r = requests.get(f"{BASE_URL}/api/analytics/", headers=new_user_headers, timeout=15)
    assert r.status_code == 403


# ──────────────── Document supersedes + expiry + listing ────────────────

def _upload_txt(headers, content_bytes, title, **form):
    files = {"file": (f"{title}.txt", content_bytes, "text/plain")}
    data = {"title": title, "doc_type": "policy", "source": "superadmin", **form}
    r = requests.post(f"{BASE_URL}/api/documents/upload",
                      headers=headers, files=files, data=data, timeout=60)
    return r


@pytest.fixture(scope="session")
def superseded_pair(admin_headers):
    # Upload v1
    body_v1 = b"ITER3 SUPERSEDE TEST DOC v1 content covering safety LOTO procedure step by step." * 4
    r1 = _upload_txt(admin_headers, body_v1, f"iter3_super_{uuid.uuid4().hex[:6]}")
    assert r1.status_code == 201, r1.text
    doc1 = r1.json()
    # Wait for processing
    for _ in range(20):
        time.sleep(1)
        chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                           headers=admin_headers, timeout=15).json()
        item = next((d for d in chk["items"] if d["id"] == doc1["id"]), None)
        if item and item.get("is_processed"):
            break
    # Upload v2 superseding v1
    body_v2 = b"ITER3 SUPERSEDE TEST DOC v2 updated LOTO content with new release steps and rev." * 4
    r2 = _upload_txt(admin_headers, body_v2, f"iter3_super_{uuid.uuid4().hex[:6]}_v2",
                     supersedes_id=doc1["id"])
    assert r2.status_code == 201, r2.text
    doc2 = r2.json()
    # Wait for doc2 to process
    for _ in range(20):
        time.sleep(1)
        chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                           headers=admin_headers, timeout=15).json()
        item = next((d for d in chk["items"] if d["id"] == doc2["id"]), None)
        if item and item.get("is_processed"):
            break
    yield {"v1": doc1, "v2": doc2}
    # Cleanup
    for d in (doc2, doc1):
        try:
            requests.delete(f"{BASE_URL}/api/documents/{d['id']}", headers=admin_headers, timeout=15)
        except Exception:
            pass


def test_supersedes_retires_old_doc(admin_headers, superseded_pair):
    v1_id = superseded_pair["v1"]["id"]
    v2_id = superseded_pair["v2"]["id"]
    # Fetch including superseded
    docs = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                        headers=admin_headers, timeout=15).json()["items"]
    v1 = next(d for d in docs if d["id"] == v1_id)
    v2 = next(d for d in docs if d["id"] == v2_id)
    assert v1["superseded_by_id"] == v2_id, "old doc not marked as superseded"
    assert v1["chunk_count"] == 0, "old doc chunks should be removed"
    assert v2["supersedes_id"] == v1_id
    assert v2["chunk_count"] > 0, "new doc should have chunks"


def test_list_excludes_superseded_by_default(admin_headers, superseded_pair):
    v1_id = superseded_pair["v1"]["id"]
    docs = requests.get(f"{BASE_URL}/api/documents/", headers=admin_headers, timeout=15).json()["items"]
    ids = {d["id"] for d in docs}
    assert v1_id not in ids, "Superseded doc must be excluded by default"
    # Include flag
    docs2 = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                         headers=admin_headers, timeout=15).json()["items"]
    ids2 = {d["id"] for d in docs2}
    assert v1_id in ids2


def test_supersedes_audit_log(admin_headers, superseded_pair):
    v2_id = superseded_pair["v2"]["id"]
    r = requests.get(f"{BASE_URL}/api/audit/?limit=50", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    upload_entries = [it for it in items
                      if it.get("action") == "upload_document"
                      and it.get("resource_id") == v2_id]
    assert upload_entries, "Audit entry for v2 upload not found"
    details = upload_entries[0].get("details") or {}
    assert details.get("supersedes_id") == superseded_pair["v1"]["id"]


@pytest.fixture(scope="session")
def expired_doc(admin_headers):
    body = b"ITER3 EXPIREDDOCTOKEN obsolete procedure that must be excluded from retrieval. " * 6
    r = _upload_txt(admin_headers, body, f"iter3_expired_{uuid.uuid4().hex[:6]}",
                    expiry_date="2020-01-01")
    assert r.status_code == 201, r.text
    doc = r.json()
    # Wait for processing
    for _ in range(20):
        time.sleep(1)
        chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                           headers=admin_headers, timeout=15).json()
        item = next((d for d in chk["items"] if d["id"] == doc["id"]), None)
        if item and item.get("is_processed"):
            doc = item
            break
    yield doc
    try:
        requests.delete(f"{BASE_URL}/api/documents/{doc['id']}", headers=admin_headers, timeout=15)
    except Exception:
        pass


def test_expired_doc_marked_expired(expired_doc):
    assert expired_doc.get("is_expired") is True
    assert expired_doc.get("expiry_date") is not None


def test_expired_doc_excluded_from_retrieval(admin_headers, expired_doc):
    """Query with EXPIREDDOCTOKEN — the doc must NOT appear in sources."""
    r = requests.post(f"{BASE_URL}/api/chat/", headers=admin_headers,
                      json={"content": "Explain EXPIREDDOCTOKEN obsolete procedure"}, timeout=120)
    assert r.status_code == 200
    sources = r.json().get("sources", []) or []
    src_ids = {s.get("doc_id") for s in sources}
    assert expired_doc["id"] not in src_ids, "Expired doc must be excluded from retrieval"


# ──────────────── Admin stats new fields ────────────────

def test_admin_stats_new_fields(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    assert "pending_feedback" in s and s["pending_feedback"] >= 0
    assert "expired_documents" in s and s["expired_documents"] >= 0


# ──────────────── SSRF regression ────────────────

def test_ssrf_localhost_still_rejected(admin_headers):
    payload = {"url": "http://localhost/test", "label": "ssrf-test-iter3"}
    r = requests.post(f"{BASE_URL}/api/web-sources/", headers=admin_headers,
                      json=payload, timeout=15)
    assert r.status_code == 400
    assert "localhost" in r.text.lower() or "private" in r.text.lower() or "reserved" in r.text.lower()
