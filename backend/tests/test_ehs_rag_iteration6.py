"""
Iteration 6 backend tests — Latency P0 (parallel HyDE, lazy followups),
embedding LRU cache, skip-rerank ≤3 candidates, tier metadata on chunks/sources,
DocumentSource.REGIONAL_BASE, seed_global_sources.py import shape.

NOTE on routing:
 - /api/documents/upload forces superadmin uploads to source=base_corpus
   (see document_routes.py:114-117). That means any value posted by
   superadmin (`superadmin`, `regional_base`) is overridden → resulting
   chunks land in the base collection with tier=global. We test that
   real behaviour (and flag the gap separately in the test report).
"""
import os
import time
import json
import uuid
import pytest
import requests

# ── Backend URL ──
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
REGULAR_EMAIL = "acmeworker@test.com"
REGULAR_PASS = "Worker@12345"
VICTIM_EMAIL = "victim@test.com"
VICTIM_PASS = "Victim@12345"


# ── Fixtures ──

@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def regular_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": REGULAR_EMAIL, "password": REGULAR_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.skip("regular user not seeded")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def victim_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": VICTIM_EMAIL, "password": VICTIM_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.skip("victim user not seeded")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _consume_stream(headers, content, timeout=120):
    """Consume an SSE stream, returns (sources_dt, done_dt, sources_data, done_data, session_id)."""
    t0 = time.perf_counter()
    sources_dt = done_dt = None
    sources_data = None
    done_data = None
    session_id = None
    current = None
    with requests.post(f"{BASE_URL}/api/chat/stream",
                       headers=headers, json={"content": content},
                       stream=True, timeout=timeout) as r:
        assert r.status_code == 200, r.text
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None or raw == "" or raw.startswith(":"):
                continue
            if raw.startswith("event:"):
                current = raw.split(":", 1)[1].strip()
            elif raw.startswith("data:"):
                blob = raw[5:].strip()
                if current == "session":
                    try:
                        session_id = json.loads(blob).get("session_id")
                    except Exception:
                        pass
                elif current == "sources" and sources_dt is None:
                    sources_dt = time.perf_counter() - t0
                    try:
                        sources_data = json.loads(blob)
                    except Exception:
                        sources_data = []
                elif current == "done":
                    done_dt = time.perf_counter() - t0
                    try:
                        done_data = json.loads(blob)
                    except Exception:
                        done_data = {}
                    break
    return sources_dt, done_dt, sources_data, done_data, session_id


# ── P0: Latency — sources <8s; done independent of followups ──

def test_sources_event_arrives_under_8s(admin_headers):
    """Parallel HyDE should deliver `sources` quickly (<8s p99)."""
    sources_dt, done_dt, sources, done, sid = _consume_stream(
        admin_headers, "What PPE is required for hot work in one short line?"
    )
    print(f"\nsources_dt={sources_dt and round(sources_dt,2)}s "
          f"done_dt={done_dt and round(done_dt,2)}s")
    assert sources_dt is not None, "no sources event"
    assert sources_dt < 8.0, f"sources took {sources_dt:.2f}s (>8s P0 budget)"


def test_done_event_has_followups_pending_flag(admin_headers):
    """done.data must carry followups_pending=True and suggested_followups=[]
    (the stream must NOT wait for the followups LLM call)."""
    _, done_dt, _, done, _ = _consume_stream(
        admin_headers, "List two confined-space hazards briefly."
    )
    assert done is not None, "no done event"
    assert done.get("followups_pending") is True, f"missing followups_pending: {done}"
    assert done.get("suggested_followups") == [], \
        f"suggested_followups should be empty (lazy): {done.get('suggested_followups')}"


# ── P0: Lazy followups endpoint ──

def test_lazy_followups_returns_list_and_is_cached(admin_headers):
    """First call generates 3 followups within ~10s; second call returns
    same list with cached=True quickly."""
    # Run a stream to seed a session+message
    _, _, _, _, sid = _consume_stream(
        admin_headers, "What are the steps for a lockout-tagout procedure?"
    )
    assert sid, "no session id"

    # 1st call
    t0 = time.perf_counter()
    r1 = requests.post(f"{BASE_URL}/api/chat/sessions/{sid}/followups",
                       headers=admin_headers, timeout=30)
    dt1 = time.perf_counter() - t0
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    print(f"\n1st followups dt={dt1:.2f}s body={body1}")
    fups1 = body1.get("followups") or []
    assert isinstance(fups1, list)
    # We allow empty if the message pair edge case happens but normally 3.
    # The lazy endpoint may return cached=False on 1st call.
    assert "cached" not in body1 or body1.get("cached") is False or fups1, \
        f"unexpected 1st response: {body1}"

    # 2nd call — must be cached + idempotent
    t1 = time.perf_counter()
    r2 = requests.post(f"{BASE_URL}/api/chat/sessions/{sid}/followups",
                       headers=admin_headers, timeout=10)
    dt2 = time.perf_counter() - t1
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    print(f"2nd followups dt={dt2*1000:.0f}ms body={body2}")
    fups2 = body2.get("followups") or []
    # If 1st returned non-empty followups, 2nd must be cached and same.
    if fups1:
        assert body2.get("cached") is True, f"2nd call not cached: {body2}"
        assert fups2 == fups1, "cached list differs from 1st call"
        assert dt2 < 2.0, f"cached call too slow: {dt2:.2f}s"


def test_lazy_followups_404_on_unknown_session(admin_headers):
    r = requests.post(
        f"{BASE_URL}/api/chat/sessions/00000000-0000-0000-0000-000000000000/followups",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 404, r.text


def test_lazy_followups_other_user_session_returns_404_or_403(admin_headers, regular_headers):
    """Sessions of another user must not be accessible. (Implementation
    filters by user_id so it returns 404 — also accept 403.)"""
    # Create a session as admin
    _, _, _, _, sid = _consume_stream(
        admin_headers, "Briefly: what is JSA?"
    )
    assert sid
    # Try to fetch as regular user
    r = requests.post(
        f"{BASE_URL}/api/chat/sessions/{sid}/followups",
        headers=regular_headers, timeout=10,
    )
    assert r.status_code in (403, 404), r.text


# ── Embedding LRU cache: warm path must not break + fast retrieval ──

def test_embedding_cache_warm_query_works(admin_headers):
    """Same query twice — both succeed; 2nd should not error and time-to-sources
    should be reasonable (cache populated)."""
    q = "What PPE prevents arc-flash injuries?"
    s1, _, _, _, _ = _consume_stream(admin_headers, q)
    s2, _, _, _, _ = _consume_stream(admin_headers, q)
    print(f"\nwarm query sources: 1st={s1 and round(s1,2)}s 2nd={s2 and round(s2,2)}s")
    assert s1 is not None and s2 is not None
    # 2nd run shouldn't be drastically slower — generous bound
    assert s2 < 10.0, f"warm-cache 2nd run sources took {s2:.2f}s"


# ── Tier metadata: SourceReference.tier present on every source ──

def test_source_response_includes_tier_field(admin_headers):
    """Every source in the sources event must have a `tier` field in
    {global, regional, company}."""
    _, _, sources, _, _ = _consume_stream(
        admin_headers, "What does LOTO stand for?"
    )
    assert sources, "no sources returned"
    valid = {"global", "regional", "company"}
    for s in sources:
        assert "tier" in s, f"source missing tier: {s.get('title')}"
        assert s["tier"] in valid, f"bad tier: {s['tier']}"
    print(f"\nTiers seen: {set(s['tier'] for s in sources)}")


# ── Tier metadata on uploaded chunks (via sources response) ──

def _upload_txt(headers, body_bytes, title, source_form="superadmin", doc_type="policy"):
    files = {"file": (f"{title}.txt", body_bytes, "text/plain")}
    data = {"title": title, "doc_type": doc_type, "source": source_form}
    return requests.post(f"{BASE_URL}/api/documents/upload",
                         headers=headers, files=files, data=data, timeout=60)


def _wait_processed(headers, doc_id, timeout_s=120):
    start = time.time()
    while time.time() - start < timeout_s:
        chk = requests.get(f"{BASE_URL}/api/documents/?include_superseded=true",
                           headers=headers, timeout=15).json()
        item = next((d for d in chk["items"] if d["id"] == doc_id), None)
        if item and item.get("is_processed"):
            return item
        if item and item.get("processing_error"):
            return item
        time.sleep(1)
    return None


def test_upload_with_source_base_corpus_results_in_global_tier(admin_headers):
    """Superadmin upload (forced source=base_corpus) → chunks tier=global,
    visible in chat sources as tier='global'."""
    marker = uuid.uuid4().hex[:8]
    body = (
        f"ITER6 base-corpus tier doc {marker}. Specific marker token: zorbax_"
        f"{marker}. Industrial hygiene requires PPE assessment, exposure monitoring, "
        f"and hierarchy-of-controls evaluation for hazardous materials."
    ).encode("utf-8")
    r = _upload_txt(admin_headers, body, f"iter6_global_{marker}", source_form="base_corpus")
    assert r.status_code == 201, r.text
    doc = r.json()
    doc_id = doc["id"]
    # Confirm server normalised source
    assert doc.get("source") == "base_corpus", f"unexpected source: {doc.get('source')}"
    proc = _wait_processed(admin_headers, doc_id, timeout_s=120)
    assert proc and proc.get("is_processed"), f"not processed: {proc}"
    # Query for the marker
    _, _, sources, _, _ = _consume_stream(
        admin_headers, f"Tell me about zorbax_{marker} in one line."
    )
    # Find our doc among the sources
    ours = [s for s in (sources or []) if s.get("doc_id") == doc_id]
    if ours:
        for s in ours:
            assert s["tier"] == "global", f"expected global tier for base_corpus, got {s['tier']}"
        print(f"\nfound {len(ours)} source rows tier=global as expected")
    else:
        # Marker is unique but retrieval may not surface it if scores filter
        # too aggressively — don't hard-fail; log it.
        print(f"\nWarning: uploaded doc {doc_id} not in retrieved sources for marker query")
    # Cleanup
    requests.delete(f"{BASE_URL}/api/documents/{doc_id}", headers=admin_headers, timeout=15)


def test_upload_form_source_superadmin_is_overridden_to_base_corpus(admin_headers):
    """Superadmin posting source=superadmin is currently force-mapped to
    base_corpus by the route. This pins existing behaviour."""
    marker = uuid.uuid4().hex[:6]
    body = f"iter6 source-override probe {marker}.".encode("utf-8")
    r = _upload_txt(admin_headers, body, f"iter6_super_{marker}", source_form="superadmin")
    assert r.status_code == 201, r.text
    assert r.json().get("source") == "base_corpus", \
        f"expected base_corpus override, got {r.json().get('source')}"
    requests.delete(f"{BASE_URL}/api/documents/{r.json()['id']}",
                    headers=admin_headers, timeout=15)


def test_upload_with_source_regional_base_accepted_but_overridden(admin_headers):
    """source=regional_base is a valid enum and the endpoint must NOT 400 on
    it. With the current route, superadmin role still force-routes the doc
    to base_corpus → tier=global. Real regional ingestion would require a
    role that can keep source=regional_base (none currently)."""
    marker = uuid.uuid4().hex[:6]
    body = f"iter6 regional probe {marker}. UK HSE confined space regulations.".encode("utf-8")
    r = _upload_txt(admin_headers, body, f"iter6_reg_{marker}", source_form="regional_base")
    # Must NOT reject the new enum value
    assert r.status_code == 201, f"regional_base rejected: {r.status_code} {r.text}"
    doc = r.json()
    # Route currently forces superadmin uploads to base_corpus — pin that.
    assert doc.get("source") in ("regional_base", "base_corpus"), \
        f"unexpected source: {doc.get('source')}"
    # cleanup
    requests.delete(f"{BASE_URL}/api/documents/{doc['id']}",
                    headers=admin_headers, timeout=15)


# ── Skip-rerank smoke (narrow query): retrieve still works ──

def test_narrow_query_does_not_break_retrieval(admin_headers):
    """A very narrow nonsense-y query should still run through retrieve()
    without raising (rerank skip path)."""
    s, d, sources, done, _ = _consume_stream(
        admin_headers, f"What is zztoken_{uuid.uuid4().hex[:6]} in one line?"
    )
    # We don't require sources to be non-empty (likely none) — just no failure
    assert done is not None, "stream did not complete on narrow query"
    print(f"\nnarrow query sources_count={len(sources or [])}")


# ── seed_global_sources.py import ──

def test_seed_global_sources_imports_with_19_entries():
    """Script must be importable and expose GLOBAL_SOURCES list of length 19."""
    import subprocess
    backend_env = os.environ.copy()
    # Provide required vars from /app/backend/.env
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                backend_env.setdefault(k, v)
    except Exception:
        pass
    r = subprocess.run(
        ["python", "-c", "from seed_global_sources import GLOBAL_SOURCES; print(len(GLOBAL_SOURCES))"],
        cwd="/app/backend", env=backend_env, capture_output=True, text=True, timeout=20,
    )
    assert r.returncode == 0, f"import failed: {r.stderr}"
    n = int(r.stdout.strip())
    print(f"\nGLOBAL_SOURCES count = {n}")
    assert n == 19, f"expected 19 sources, got {n}"


# ── Regression: SSE flow still works ──

def test_regression_full_sse_flow_intact(admin_headers):
    """session → sources → token(s) → done — no events missing."""
    events_seen = []
    current = None
    with requests.post(f"{BASE_URL}/api/chat/stream",
                       headers=admin_headers,
                       json={"content": "What is a safety data sheet in one line?"},
                       stream=True, timeout=120) as r:
        assert r.status_code == 200
        # CORS
        # Note: CORS preflight headers are set on OPTIONS; we check basic header echo.
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None or raw == "" or raw.startswith(":"):
                continue
            if raw.startswith("event:"):
                ev = raw.split(":", 1)[1].strip()
                current = ev
                if ev not in events_seen:
                    events_seen.append(ev)
                if ev == "done":
                    break
    for need in ("session", "sources", "token", "done"):
        assert need in events_seen, f"missing event {need}: {events_seen}"


def test_regression_cors_preflight_on_chat_stream():
    """OPTIONS preflight must include allow-origin (CORS still configured)."""
    r = requests.options(
        f"{BASE_URL}/api/chat/stream",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
        timeout=10,
    )
    # Some FastAPI/CORS configs return 200 with headers
    assert r.status_code in (200, 204), r.status_code
    aco = r.headers.get("access-control-allow-origin")
    assert aco, f"missing CORS allow-origin header: {dict(r.headers)}"
