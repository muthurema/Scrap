"""
Iteration 7 backend tests — verifies:
  1. Source filtering: chat/stream `sources` SSE event payload shape
     `{sources: [...company-only...], external_count: N}` (was a bare list).
  2. Superadmin (no company) gets sources=[], external_count>=0.
  3. GET /api/documents/{doc_id} metadata fetch (200 / 404 / 403 cross-tenant).
  4. GET /api/documents/{doc_id}/download streams inline (200 + Content-Disposition / 404 / 403).
  5. Hybrid Anthropic path: _litellm_params branches on ANTHROPIC_API_KEY.
  6. Regression: done event still emits followups_pending=true; CORS preflight; upload/delete.
"""
import io
import json
import os
import sys
import uuid

import pytest
import requests

# Make backend app importable for the rag_engine unit branch test
sys.path.insert(0, "/app/backend")

# Load backend .env so importing app.config / app.rag_engine doesn't fail-fast
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ehs-rag-chat.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPERADMIN = {"email": "admin@ehsrag.com", "password": "Admin@12345"}
ACME_ADMIN = {"email": "acmeadmin@test.com", "password": "Acme@12345"}
ACME_WORKER = {"email": "acmeworker@test.com", "password": "Worker@12345"}


# ── Auth helpers ─────────────────────────────────────────────────────────────

def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdrs(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def super_tok():
    return _login(SUPERADMIN)


@pytest.fixture(scope="module")
def acme_admin_tok():
    return _login(ACME_ADMIN)


@pytest.fixture(scope="module")
def acme_worker_tok():
    return _login(ACME_WORKER)


# Create a second company + admin to test cross-tenant 403
@pytest.fixture(scope="module")
def other_company_admin_tok(super_tok):
    # 1. Superadmin creates a new company
    cname = f"TEST_OtherCo_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{API}/admin/companies", headers=_hdrs(super_tok),
                      json={"name": cname}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"Cannot create company: {r.status_code} {r.text}")
    company = r.json()
    cid = company.get("id") or company.get("company_id")

    # 2. Create admin invite for that company (only superadmin can mint admins)
    r2 = requests.post(f"{API}/team/invites",
                       headers=_hdrs(super_tok),
                       json={"role": "admin", "company_id": cid,
                             "max_uses": 5, "expires_in_days": 7}, timeout=30)
    if r2.status_code not in (200, 201):
        pytest.skip(f"Cannot create invite: {r2.status_code} {r2.text}")
    invite_code = r2.json().get("code") or r2.json().get("invite_code")

    # 3. Register a new admin
    email = f"TEST_otheradmin_{uuid.uuid4().hex[:6]}@test.com"
    password = "Other@12345"
    r3 = requests.post(f"{API}/auth/register",
                       json={"email": email, "password": password,
                             "full_name": "Other Admin",
                             "invite_code": invite_code}, timeout=30)
    if r3.status_code not in (200, 201):
        pytest.skip(f"Cannot register other-co admin: {r3.status_code} {r3.text}")
    tok = _login({"email": email, "password": password})
    yield {"tok": tok, "company_id": cid, "email": email}


# ── Fixture: Acme admin uploads a doc, yields doc_id, cleans up ──────────────

@pytest.fixture(scope="module")
def acme_doc(acme_admin_tok):
    content = b"Acme company-only test doc. Confined space PPE: SCBA, harness, gas meter. ITER7."
    files = {"file": ("iter7_acme_secret.txt", io.BytesIO(content), "text/plain")}
    data = {"title": "ITER7 Acme Confined Space SOP", "doc_type": "sop"}
    r = requests.post(f"{API}/documents/upload", headers=_hdrs(acme_admin_tok),
                      files=files, data=data, timeout=60)
    assert r.status_code == 201, f"upload failed: {r.status_code} {r.text}"
    doc = r.json()
    doc_id = doc["id"]
    yield doc
    # cleanup
    try:
        requests.delete(f"{API}/documents/{doc_id}", headers=_hdrs(acme_admin_tok), timeout=30)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  1. GET /api/documents/{doc_id}  — metadata endpoint
# ═══════════════════════════════════════════════════════════════════════════

class TestGetDocumentMetadata:
    def test_owner_can_fetch_metadata(self, acme_admin_tok, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}",
                         headers=_hdrs(acme_admin_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == acme_doc["id"]
        assert body["original_filename"] == "iter7_acme_secret.txt"
        # No raw mongo _id leaked
        assert "_id" not in body

    def test_404_on_missing_doc(self, acme_admin_tok):
        r = requests.get(f"{API}/documents/does-not-exist-{uuid.uuid4().hex}",
                         headers=_hdrs(acme_admin_tok), timeout=30)
        assert r.status_code == 404

    def test_cross_tenant_403(self, other_company_admin_tok, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}",
                         headers=_hdrs(other_company_admin_tok["tok"]), timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_superadmin_can_fetch_any(self, super_tok, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}",
                         headers=_hdrs(super_tok), timeout=30)
        assert r.status_code == 200

    def test_unauthenticated_rejected(self, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}", timeout=30)
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
#  2. GET /api/documents/{doc_id}/download
# ═══════════════════════════════════════════════════════════════════════════

class TestDownloadDocument:
    def test_owner_can_download_inline(self, acme_admin_tok, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}/download",
                         headers=_hdrs(acme_admin_tok), timeout=30)
        assert r.status_code == 200, r.text
        cd = r.headers.get("Content-Disposition", "")
        assert "inline" in cd.lower(), f"expected inline disposition, got: {cd}"
        assert "iter7_acme_secret.txt" in cd
        assert b"ITER7" in r.content

    def test_download_404_on_missing(self, acme_admin_tok):
        r = requests.get(f"{API}/documents/missing-{uuid.uuid4().hex}/download",
                         headers=_hdrs(acme_admin_tok), timeout=30)
        assert r.status_code == 404

    def test_download_cross_tenant_403(self, other_company_admin_tok, acme_doc):
        r = requests.get(f"{API}/documents/{acme_doc['id']}/download",
                         headers=_hdrs(other_company_admin_tok["tok"]), timeout=30)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  3. Chat SSE — sources event new envelope shape
# ═══════════════════════════════════════════════════════════════════════════

def _consume_sse(tok, query, timeout=60):
    """POST /chat/stream, return parsed events list."""
    r = requests.post(f"{API}/chat/stream",
                      headers={**_hdrs(tok), "Accept": "text/event-stream"},
                      json={"content": query}, timeout=timeout, stream=True)
    assert r.status_code == 200, f"stream HTTP {r.status_code}: {r.text[:300]}"
    events = []
    current_event = None
    for line in r.iter_lines(decode_unicode=True):
        if line is None:
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:") and current_event:
            data_str = line[len("data:"):].strip()
            try:
                data = json.loads(data_str)
            except Exception:
                data = data_str
            events.append({"type": current_event, "data": data})
            if current_event == "done":
                break
        elif line == "":
            current_event = None
    r.close()
    return events


class TestSourcesEnvelope:
    def test_sources_payload_is_object_with_envelope(self, acme_worker_tok):
        evts = _consume_sse(acme_worker_tok, "What PPE is required for confined space entry?")
        types = [e["type"] for e in evts]
        assert "session" in types
        assert "sources" in types
        assert "done" in types

        src_evt = next(e for e in evts if e["type"] == "sources")
        data = src_evt["data"]
        # CORE assertion: dict, not bare list
        assert isinstance(data, dict), f"sources data must be dict envelope, got {type(data).__name__}"
        assert "sources" in data
        assert "external_count" in data
        assert isinstance(data["sources"], list)
        assert isinstance(data["external_count"], int)
        assert data["external_count"] >= 0
        # every source returned must be tier=company (worker has Acme company_id)
        for s in data["sources"]:
            assert s.get("tier") == "company", f"non-company tier leaked to wire: {s.get('tier')}"

    def test_superadmin_has_no_company_sources(self, super_tok):
        evts = _consume_sse(super_tok, "What PPE is required for confined space entry?")
        src_evt = next(e for e in evts if e["type"] == "sources")
        data = src_evt["data"]
        assert isinstance(data, dict)
        # Superadmin has no company → sources list is empty, but external context exists
        assert data["sources"] == []
        # external_count may be 0 if KB is empty, but normally >0 for this canonical query
        assert data["external_count"] >= 0

    def test_done_event_has_followups_pending(self, acme_worker_tok):
        evts = _consume_sse(acme_worker_tok, "What is JSA?")
        done_evt = next(e for e in evts if e["type"] == "done")
        d = done_evt["data"]
        assert d.get("followups_pending") is True
        assert d.get("suggested_followups") == []
        assert "final_text" in d


# ═══════════════════════════════════════════════════════════════════════════
#  4. _litellm_params branching (Anthropic key absent → proxy)
# ═══════════════════════════════════════════════════════════════════════════

class TestLitellmParamsBranching:
    def test_proxy_path_when_anthropic_key_unset(self, monkeypatch):
        # Ensure unset
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Force fresh Settings
        from app.config import get_settings
        get_settings.cache_clear()
        from app.rag_engine import _litellm_params
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]
        params = _litellm_params(msgs)
        assert params["custom_llm_provider"] == "openai"
        assert "api_base" in params and params["api_base"].endswith("/llm")
        # Model must NOT be prefixed with anthropic/
        assert not params["model"].startswith("anthropic/")
        # extra_headers w/ prompt-caching should NOT be present
        assert "extra_headers" not in params

    def test_direct_anthropic_path_when_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-fake")
        from app.config import get_settings
        get_settings.cache_clear()
        # rag_engine has a module-level `settings = get_settings()` that was
        # already evaluated at import time — reload the module so the new
        # settings (with the env-var-derived anthropic_api_key) take effect.
        import importlib, app.rag_engine as rag_mod
        importlib.reload(rag_mod)
        _litellm_params = rag_mod._litellm_params
        msgs = [{"role": "system", "content": "long static EHS system prompt"},
                {"role": "user", "content": "u"}]
        params = _litellm_params(msgs)
        assert params["model"].startswith("anthropic/"), params["model"]
        assert params["api_key"] == "sk-test-anthropic-fake"
        assert "custom_llm_provider" not in params
        # system message converted to content-block array w/ cache_control
        sys_msg = params["messages"][0]
        assert sys_msg["role"] == "system"
        assert isinstance(sys_msg["content"], list)
        assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
        # prompt-caching beta header
        assert params["extra_headers"]["anthropic-beta"].startswith("prompt-caching")

        # Restore
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        get_settings.cache_clear()
        importlib.reload(rag_mod)


# ═══════════════════════════════════════════════════════════════════════════
#  5. Regression: CORS + document delete + tier on chunks metadata
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression:
    def test_cors_preflight_on_chat_stream(self):
        r = requests.options(f"{API}/chat/stream", headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }, timeout=15)
        # Either 200 or 204; key check is the header presence
        assert r.status_code in (200, 204), r.status_code
        assert r.headers.get("access-control-allow-origin") is not None

    def test_document_upload_and_delete_roundtrip(self, acme_admin_tok):
        content = b"ITER7 regression delete check"
        files = {"file": ("iter7_delete_me.txt", io.BytesIO(content), "text/plain")}
        r = requests.post(f"{API}/documents/upload", headers=_hdrs(acme_admin_tok),
                          files=files, data={"title": "ITER7 delete me", "doc_type": "general"},
                          timeout=60)
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]
        # confirm metadata reachable
        rg = requests.get(f"{API}/documents/{doc_id}", headers=_hdrs(acme_admin_tok), timeout=30)
        assert rg.status_code == 200
        # delete
        rd = requests.delete(f"{API}/documents/{doc_id}", headers=_hdrs(acme_admin_tok), timeout=30)
        assert rd.status_code in (200, 204)
        # confirm gone
        rg2 = requests.get(f"{API}/documents/{doc_id}", headers=_hdrs(acme_admin_tok), timeout=30)
        assert rg2.status_code == 404
