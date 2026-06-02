import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { UploadSimple, ArrowsClockwise, Trash, CheckCircle, Warning, Hourglass, ArrowsLeftRight, Clock, X as XIcon } from "@phosphor-icons/react";

const DOC_TYPES = [
  ["general", "General"], ["sop", "SOP / Procedure"], ["incident_report", "Incident Report"],
  ["risk_assessment", "Risk / HAZOP"], ["regulatory", "Regulatory (ISO/OSHA)"],
  ["training", "Training"], ["permit", "Permit"], ["policy", "Policy"], ["msds", "MSDS / SDS"],
];

const SOURCES = [
  ["superadmin", "Company (Superadmin)"],
  ["base_corpus", "Global — base corpus (no jurisdiction)"],
  ["regional_base", "Regional — jurisdiction-specific (requires jurisdiction)"],
];

const JURISDICTIONS = ["", "US", "UK", "EU", "AU", "IN", "CA", "GLOBAL"];

export default function DocumentsPage() {
  const PAGE_SIZE = 100;
  const [docs, setDocs] = useState([]);
  const [totalDocs, setTotalDocs] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const fileRef = useRef(null);
  const sentinelRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null); // { current, total, currentName, failed: [] }
  const uploadAbortRef = useRef(null);
  const cancelRequestedRef = useRef(false);

  const [form, setForm] = useState({
    title: "", description: "", doc_type: "general", source: "superadmin",
    tags: "", version: "", expiry_date: "", jurisdiction: "",
  });
  const [replacingDoc, setReplacingDoc] = useState(null);
  // Concurrent-ingestion gating. Backend caps in-flight docs at 5 per scope;
  // we additionally block the *next batch* until the current batch reaches 0.
  const [quota, setQuota] = useState({ inflight: 0, max: 5, remaining: 5, can_upload: true });
  const [selectedCount, setSelectedCount] = useState(0);

  const MAX_BATCH = 5;

  const loadQuota = async () => {
    try {
      const { data } = await api.get("/documents/upload-quota");
      setQuota(data);
    } catch (_e) { /* admin role may not allow — silent */ }
  };

  // Reload from page 1 (used after upload / delete / cancel / first mount + poll)
  const load = async () => {
    try {
      const [docsR] = await Promise.all([
        api.get(`/documents/?page=1&page_size=${PAGE_SIZE}`),
        loadQuota(),
      ]);
      const data = docsR.data;
      setDocs(data.items);
      setTotalDocs(data.total ?? data.items.length);
      setPage(1);
      setHasMore(data.items.length < (data.total ?? 0));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Append next page (used by Load more button + infinite scroll sentinel)
  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const nextPage = page + 1;
      const { data } = await api.get(`/documents/?page=${nextPage}&page_size=${PAGE_SIZE}`);
      setDocs((prev) => {
        // Dedupe in case a doc appeared on both pages due to a concurrent upload
        const seen = new Set(prev.map((d) => d.id));
        const fresh = data.items.filter((d) => !seen.has(d.id));
        return [...prev, ...fresh];
      });
      setTotalDocs(data.total ?? totalDocs);
      setPage(nextPage);
      // hasMore stays true until we've fetched as many items as total reports
      setHasMore((prev) => {
        const fetchedSoFar = docs.length + data.items.length;
        return fetchedSoFar < (data.total ?? 0);
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  };

  // Initial load
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Lightweight refresh of the first page every 5s — only updates statuses of
  // already-shown docs (in-flight PROCESSING transitions). Doesn't touch the
  // user's loaded-more state or scroll position.
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const [docsR] = await Promise.all([
          api.get(`/documents/?page=1&page_size=${PAGE_SIZE}`),
          loadQuota(),
        ]);
        const data = docsR.data;
        setTotalDocs(data.total ?? 0);
        setDocs((prev) => {
          const updateMap = new Map(data.items.map((d) => [d.id, d]));
          // Merge fresh data into existing rows; keep loaded-more rows intact
          const merged = prev.map((d) => updateMap.get(d.id) || d);
          // Append any brand-new docs (uploads) that aren't yet in the list
          const seen = new Set(prev.map((d) => d.id));
          const fresh = data.items.filter((d) => !seen.has(d.id));
          return [...fresh, ...merged];
        });
      } catch (e) {
        // Silent fail — this is a 5-second poll; next tick retries. Log so
        // recurring issues are visible in the browser console without
        // toast-spamming the user.
        if (process.env.NODE_ENV !== "production") {
          console.warn("[documents] background poll failed:", e?.message);
        }
      }
    }, 5000);
    return () => clearInterval(t);
  }, []);

  // Infinite scroll — when sentinel comes into view, fetch next page
  useEffect(() => {
    if (!sentinelRef.current || !hasMore) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) loadMore();
    }, { rootMargin: "200px" });
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, page, loadingMore]);

  const cancelInflightUpload = () => {
    cancelRequestedRef.current = true;
    try { uploadAbortRef.current?.abort(); } catch (_) {}
    toast.message("Cancelling upload…");
  };

  const cancelIngestion = async (docId, title) => {
    if (!confirm(`Cancel ingestion of "${title}"? The file will be removed and you can re-upload.`)) return;
    try {
      await api.post(`/documents/${docId}/cancel`);
      toast.success("Cancelled — file removed");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cancel failed");
    }
  };

  const onFilesChosen = () => {
    const files = Array.from(fileRef.current?.files || []);
    if (files.length > MAX_BATCH) {
      toast.warning(
        `Only ${MAX_BATCH} files can be uploaded per batch. The first ${MAX_BATCH} will be used.`,
        { duration: 6000 },
      );
    }
    setSelectedCount(Math.min(files.length, MAX_BATCH));
  };

  const upload = async (e) => {
    e.preventDefault();
    const allFiles = Array.from(fileRef.current?.files || []);
    if (allFiles.length === 0) { toast.error("Pick at least one file"); return; }

    // Enforce the per-batch cap on the client too (server enforces a hard
    // 5-in-flight cap, but slicing here gives a cleaner UX message).
    const files = replacingDoc ? allFiles.slice(0, 1) : allFiles.slice(0, MAX_BATCH);

    // Replace flow accepts a single file
    if (replacingDoc && files.length > 1) {
      toast.error("Replacement supports one file at a time");
      return;
    }

    setBusy(true);
    cancelRequestedRef.current = false;
    const failed = [];

    for (let i = 0; i < files.length; i++) {
      if (cancelRequestedRef.current) {
        failed.push({ name: files[i].name, error: "Cancelled by user" });
        for (let j = i + 1; j < files.length; j++) failed.push({ name: files[j].name, error: "Skipped (cancelled)" });
        break;
      }
      const file = files[i];
      setUploadProgress({ current: i + 1, total: files.length, currentName: file.name, failed: [...failed] });
      const fd = new FormData();
      fd.append("file", file);
      // For multi-file uploads, only apply the explicit title to the first file (or none) and let the backend infer from filename
      if (files.length === 1 && form.title) fd.append("title", form.title);
      if (form.description) fd.append("description", form.description);
      fd.append("doc_type", form.doc_type);
      fd.append("source", form.source);
      if (form.tags) fd.append("tags", form.tags);
      if (form.version) fd.append("version", form.version);
      if (form.expiry_date) fd.append("expiry_date", form.expiry_date);
      if (form.jurisdiction) fd.append("jurisdiction", form.jurisdiction);
      if (replacingDoc) fd.append("supersedes_id", replacingDoc.id);

      const controller = new AbortController();
      uploadAbortRef.current = controller;
      try {
        await api.post("/documents/upload", fd, {
          headers: { "Content-Type": "multipart/form-data" },
          signal: controller.signal,
        });
      } catch (err) {
        if (err?.name === "CanceledError" || err?.code === "ERR_CANCELED") {
          failed.push({ name: file.name, error: "Cancelled by user" });
        } else {
          failed.push({ name: file.name, error: err?.response?.data?.detail || err.message || "Upload failed" });
        }
      } finally {
        uploadAbortRef.current = null;
      }
    }

    setUploadProgress(null);
    setBusy(false);
    cancelRequestedRef.current = false;

    const successCount = files.length - failed.length;
    if (failed.length === 0) {
      toast.success(
        replacingDoc
          ? `Replaced "${replacingDoc.title}" — old version retired`
          : (files.length === 1 ? "Uploaded — processing in background" : `Uploaded ${successCount} files — processing in background`)
      );
      setOpen(false);
      setReplacingDoc(null);
      setForm({ title: "", description: "", doc_type: "general", source: "superadmin", tags: "", version: "", expiry_date: "", jurisdiction: "" });
      if (fileRef.current) fileRef.current.value = "";
    } else {
      // Group failures by reason to surface useful guidance instead of one cryptic toast
      const byReason = failed.reduce((acc, f) => {
        const err = f.error || "";
        const key = err.includes("exceeds") && err.includes("MB limit") ? "too_large"
                  : err.includes("not supported") ? "unsupported_type"
                  : "other";
        (acc[key] = acc[key] || []).push(f);
        return acc;
      }, {});
      const summary = [
        successCount > 0 ? `${successCount} uploaded` : null,
        byReason.too_large ? `${byReason.too_large.length} too large` : null,
        byReason.unsupported_type ? `${byReason.unsupported_type.length} wrong file type` : null,
        byReason.other ? `${byReason.other.length} other error` : null,
      ].filter(Boolean).join(" · ");
      toast.error(summary, {
        description: failed.slice(0, 6).map((f) => `${f.name}: ${(f.error || "").slice(0, 100)}`).join("\n") + (failed.length > 6 ? `\n…and ${failed.length - 6} more` : ""),
        duration: 15000,
      });
    }
    load();
  };

  const openReplace = (doc) => {
    setReplacingDoc(doc);
    setForm({
      ...form,
      title: doc.title || "",
      doc_type: doc.doc_type || "general",
      source: doc.source || "superadmin",
      tags: (doc.tags || []).join(", "),
      version: "",
      expiry_date: "",
      jurisdiction: doc.jurisdiction || "",
    });
    setOpen(true);
  };

  const reprocess = async (id) => {
    try {
      await api.post(`/documents/${id}/reprocess`);
      toast.success("Re-processing started");
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  const removeDoc = async (id) => {
    if (!confirm("Delete this document and all its chunks?")) return;
    try {
      await api.delete(`/documents/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl" data-testid="documents-page">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">Knowledge base</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 mb-1">Documents</h1>
          <p className="text-slate-600 text-sm sm:text-base">Upload, classify and manage the EHS document corpus.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button
              data-testid="open-upload-dialog-btn"
              disabled={!quota.can_upload && !replacingDoc}
              title={!quota.can_upload ? `${quota.inflight} document(s) still processing — wait until they finish` : undefined}
              className="rounded-sm bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 disabled:cursor-not-allowed text-white h-10 self-start sm:self-auto"
            >
              <UploadSimple size={16} weight="bold" />
              <span className="ml-2 font-semibold tracking-tight">
                {!quota.can_upload
                  ? `WAIT — ${quota.inflight} PROCESSING`
                  : "UPLOAD DOCUMENT"}
              </span>
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl w-[calc(100%-2rem)] rounded-sm border-slate-300 max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="font-bold tracking-tight">Upload EHS Document</DialogTitle>
              <DialogDescription className="text-xs text-slate-500">
                Upload a PDF, DOCX, XLSX, TXT, CSV or Markdown file. It will be parsed, classified and embedded into the knowledge base for retrieval.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={upload} className="space-y-4" data-testid="upload-form">
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">
                  {replacingDoc ? "File (PDF / DOCX / XLSX / TXT / CSV / MD)" : "Files (PDF / DOCX / XLSX / TXT / CSV / MD) — select multiple to bulk upload"}
                </Label>
                <input
                  ref={fileRef}
                  type="file"
                  required
                  multiple={!replacingDoc}
                  accept=".pdf,.docx,.xlsx,.xls,.txt,.csv,.md"
                  data-testid="upload-file-input"
                  onChange={onFilesChosen}
                  className="block w-full text-sm border border-slate-300 rounded-sm file:mr-3 file:py-2 file:px-3 file:bg-slate-900 file:text-white file:border-0 file:font-medium file:cursor-pointer hover:file:bg-slate-800"
                />
                {!replacingDoc && (
                  <div className="text-[11px] text-slate-500 leading-snug">
                    Bulk upload: hold <span className="font-mono font-semibold">Ctrl</span> / <span className="font-mono font-semibold">⌘</span> in the file picker to select up to <span className="font-mono font-semibold">{MAX_BATCH}</span> files at once. Settings (type, source, tags, jurisdiction) apply to every file in the batch.
                    {selectedCount > 0 && (
                      <span className="ml-1 font-mono font-semibold text-slate-700">
                        · {selectedCount}/{MAX_BATCH} selected
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Document Type</Label>
                  <Select value={form.doc_type} onValueChange={(v) => setForm({ ...form, doc_type: v })}>
                    <SelectTrigger className="rounded-sm" data-testid="upload-doc-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DOC_TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Source / Priority</Label>
                  <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
                    <SelectTrigger className="rounded-sm" data-testid="upload-source">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SOURCES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Title (optional)</Label>
                <Input
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="rounded-sm border-slate-300"
                  data-testid="upload-title"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Tags (comma-separated)</Label>
                <Input
                  placeholder="ISO 45001, chemical, confined space"
                  value={form.tags}
                  onChange={(e) => setForm({ ...form, tags: e.target.value })}
                  className="rounded-sm border-slate-300"
                  data-testid="upload-tags"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Description (optional)</Label>
                <Textarea
                  rows={2}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="rounded-sm border-slate-300"
                  data-testid="upload-description"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Expiry date (optional)</Label>
                  <Input
                    type="date"
                    value={form.expiry_date}
                    onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
                    className="rounded-sm border-slate-300"
                    data-testid="upload-expiry"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Jurisdiction (optional)</Label>
                  <Select value={form.jurisdiction} onValueChange={(v) => setForm({ ...form, jurisdiction: v === "_none" ? "" : v })}>
                    <SelectTrigger className="rounded-sm" data-testid="upload-jurisdiction">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">—</SelectItem>
                      {JURISDICTIONS.filter(Boolean).map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {replacingDoc && (
                <div className="bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900">
                  <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider mb-1">
                    <ArrowsLeftRight size={12} weight="bold" /> Replacing
                  </div>
                  <div>"{replacingDoc.title}" — the old version's chunks will be retired from retrieval after the new version is processed.</div>
                </div>
              )}
              {uploadProgress && (
                <div className="bg-blue-50 border border-blue-200 p-3 text-xs text-blue-900" data-testid="upload-progress">
                  <div className="flex items-center justify-between font-mono uppercase tracking-wider text-[10px] mb-1.5">
                    <span>Uploading {uploadProgress.current} / {uploadProgress.total}</span>
                    <div className="flex items-center gap-2">
                      <span>{Math.round((uploadProgress.current / uploadProgress.total) * 100)}%</span>
                      <button
                        type="button"
                        onClick={cancelInflightUpload}
                        data-testid="cancel-upload-btn"
                        className="px-2 py-0.5 border border-rose-300 bg-white hover:bg-rose-50 text-rose-700 font-mono text-[10px] uppercase tracking-wider transition-colors"
                        title="Abort the current upload and skip any remaining files"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                  <div className="h-1.5 bg-blue-100 rounded-sm overflow-hidden mb-2">
                    <div
                      className="h-full bg-blue-600 transition-all duration-300"
                      style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
                    />
                  </div>
                  <div className="truncate text-blue-800">{uploadProgress.currentName}</div>
                  {uploadProgress.failed.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-blue-200 text-rose-700">
                      <span className="font-mono uppercase tracking-wider text-[10px]">{uploadProgress.failed.length} failed:</span>{" "}
                      {uploadProgress.failed.map((f) => f.name).join(", ")}
                    </div>
                  )}
                </div>
              )}
              {!quota.can_upload && !replacingDoc && (
                <div className="bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900" data-testid="upload-blocked-banner">
                  <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider mb-1">
                    <Hourglass size={12} weight="bold" /> Wait — batch in progress
                  </div>
                  <div>
                    {quota.inflight} document{quota.inflight === 1 ? "" : "s"} still being chunked.
                    To protect server memory, you can upload the next batch only once these
                    are fully processed. Max {quota.max} documents per batch.
                  </div>
                </div>
              )}
              <Button
                type="submit"
                disabled={busy || (!quota.can_upload && !replacingDoc)}
                data-testid="submit-upload-btn"
                className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 disabled:cursor-not-allowed text-white h-10 font-semibold tracking-tight"
              >
                {busy
                  ? (uploadProgress ? `UPLOADING ${uploadProgress.current}/${uploadProgress.total}…` : (replacingDoc ? "REPLACING..." : "UPLOADING..."))
                  : (!quota.can_upload && !replacingDoc)
                    ? `WAIT — ${quota.inflight} PROCESSING`
                    : (replacingDoc ? "UPLOAD REPLACEMENT" : `UPLOAD & PROCESS (MAX ${MAX_BATCH})`)}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="mb-2 flex items-center gap-3 text-xs font-mono uppercase tracking-wider text-slate-500" data-testid="docs-count">
        Showing <span className="text-slate-900 font-bold">{docs.length}</span> of <span className="text-slate-900 font-bold">{totalDocs}</span> documents
        {totalDocs > docs.length && (
          <span className="text-amber-700 normal-case lowercase tracking-normal">
            · {totalDocs - docs.length} more — scroll down or click "Load more"
          </span>
        )}
      </div>
      <div className="border border-slate-300 bg-white overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Title</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Type</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Source</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Status</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Chunks</th>
              <th className="text-right px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && docs.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">LOADING...</td></tr>
            )}
            {!loading && docs.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">No documents yet. Upload the first one.</td></tr>
            )}
            {docs.map((d) => (
              <tr key={d.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`doc-row-${d.id}`}>
                <td className="px-3 py-2.5">
                  <div className="font-medium text-slate-900 truncate max-w-md">{d.title || d.original_filename}</div>
                  <div className="text-xs text-slate-500 font-mono truncate max-w-md">{d.original_filename}</div>
                </td>
                <td className="px-3 py-2.5">
                  <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 border border-slate-200 text-slate-700">
                    {(DOC_TYPES.find(([v]) => v === d.doc_type)?.[1] || d.doc_type)}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 border border-slate-200 text-slate-700">
                    {d.source}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge doc={d} />
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-slate-700">{d.chunk_count}</td>
                <td className="px-3 py-2.5 text-right">
                  <div className="inline-flex gap-1">
                    {!d.is_processed && !d.processing_error && (
                      <button
                        onClick={() => cancelIngestion(d.id, d.title || d.original_filename)}
                        data-testid={`cancel-ingestion-${d.id}`}
                        title="Cancel ingestion (removes file)"
                        className="p-1.5 text-slate-500 hover:text-rose-700 border border-transparent hover:border-rose-200 hover:bg-rose-50 transition-colors"
                      >
                        <XIcon size={14} weight="bold" />
                      </button>
                    )}
                    <button
                      onClick={() => openReplace(d)}
                      data-testid={`replace-${d.id}`}
                      title="Replace with new version"
                      className="p-1.5 text-slate-500 hover:text-amber-700 border border-transparent hover:border-amber-200 hover:bg-amber-50 transition-colors"
                    >
                      <ArrowsLeftRight size={14} weight="bold" />
                    </button>
                    <button
                      onClick={() => reprocess(d.id)}
                      data-testid={`reprocess-${d.id}`}
                      title="Re-process"
                      className="p-1.5 text-slate-500 hover:text-blue-700 border border-transparent hover:border-blue-200 hover:bg-blue-50 transition-colors"
                    >
                      <ArrowsClockwise size={14} weight="bold" />
                    </button>
                    <button
                      onClick={() => removeDoc(d.id)}
                      data-testid={`delete-${d.id}`}
                      title="Delete"
                      className="p-1.5 text-slate-500 hover:text-rose-700 border border-transparent hover:border-rose-200 hover:bg-rose-50 transition-colors"
                    >
                      <Trash size={14} weight="bold" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      {/* Infinite-scroll sentinel + manual Load more fallback */}
      {hasMore && (
        <div ref={sentinelRef} className="mt-4 flex justify-center" data-testid="load-more-sentinel">
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            data-testid="load-more-btn"
            className="px-4 py-2 border border-slate-300 hover:border-slate-500 bg-white hover:bg-slate-50 font-mono text-xs uppercase tracking-wider text-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingMore
              ? "LOADING…"
              : `LOAD MORE (${totalDocs - docs.length} REMAINING)`}
          </button>
        </div>
      )}
      {!hasMore && docs.length > 0 && totalDocs > PAGE_SIZE && (
        <div className="mt-4 text-center font-mono text-[10px] uppercase tracking-wider text-slate-400" data-testid="end-of-list">
          End of list · {docs.length} docs shown
        </div>
      )}
    </div>
  );
}

function StatusBadge({ doc }) {
  if (doc.is_expired) {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-800" title={`Expired ${doc.expiry_date}`}>
        <Clock size={11} weight="bold" /> EXPIRED
      </span>
    );
  }
  if (doc.processing_error) {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-rose-50 border border-rose-200 text-rose-700" title={doc.processing_error}>
        <Warning size={11} weight="bold" /> ERROR
      </span>
    );
  }
  if (doc.is_processed) {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-700">
        <CheckCircle size={11} weight="bold" /> READY
      </span>
    );
  }

  // PROCESSING — show elapsed time and flag stuck uploads
  const uploaded = doc.created_at ? new Date(doc.created_at).getTime() : Date.now();
  const elapsedSec = Math.max(0, Math.floor((Date.now() - uploaded) / 1000));
  const fmt = elapsedSec < 60
    ? `${elapsedSec}s`
    : elapsedSec < 3600
      ? `${Math.floor(elapsedSec / 60)}m${elapsedSec % 60 ? ` ${elapsedSec % 60}s` : ""}`
      : `${Math.floor(elapsedSec / 3600)}h ${Math.floor((elapsedSec % 3600) / 60)}m`;

  // Heuristic: small files (<5 MB) should process in <2 min, large ones (PDF textbooks)
  // can take 5-15 min. Anything past 15 min is almost certainly stuck.
  const sizeMB = (doc.file_size_bytes || 0) / (1024 * 1024);
  const expectedSec = Math.max(60, Math.min(15 * 60, sizeMB * 10)); // 10s per MB, clamped
  const isStuck = elapsedSec > Math.max(15 * 60, expectedSec * 2);
  const isSlow = !isStuck && elapsedSec > expectedSec;

  if (isStuck) {
    return (
      <span
        className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-rose-50 border border-rose-200 text-rose-700"
        title={`No progress for ${fmt}. The ingestion worker may have crashed or the file is malformed. Try Reprocess.`}
      >
        <Warning size={11} weight="bold" /> STUCK · {fmt}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 ${
        isSlow
          ? "bg-amber-100 border border-amber-300 text-amber-900"
          : "bg-amber-50 border border-amber-200 text-amber-700"
      }`}
      title={`Processing for ${fmt}. ${sizeMB.toFixed(1)}MB file — typical: ${Math.round(expectedSec)}s.`}
    >
      <Hourglass size={11} weight="bold" className={isSlow ? "" : "animate-pulse"} /> PROCESSING · {fmt}
    </span>
  );
}
