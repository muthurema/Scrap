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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { UploadSimple, ArrowsClockwise, Trash, CheckCircle, Warning, Hourglass, ArrowsLeftRight, Clock } from "@phosphor-icons/react";

const DOC_TYPES = [
  ["general", "General"], ["sop", "SOP / Procedure"], ["incident_report", "Incident Report"],
  ["risk_assessment", "Risk / HAZOP"], ["regulatory", "Regulatory (ISO/OSHA)"],
  ["training", "Training"], ["permit", "Permit"], ["policy", "Policy"], ["msds", "MSDS / SDS"],
];

const SOURCES = [
  ["superadmin", "Company (Superadmin)"],
  ["base_corpus", "Base Corpus (Global)"],
];

const JURISDICTIONS = ["", "US", "UK", "EU", "AU", "IN", "CA", "GLOBAL"];

export default function DocumentsPage() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    title: "", description: "", doc_type: "general", source: "superadmin",
    tags: "", version: "",
  });

  const load = async () => {
    try {
      const { data } = await api.get("/documents/");
      setDocs(data.items);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const upload = async (e) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) { toast.error("Pick a file first"); return; }
    const fd = new FormData();
    fd.append("file", file);
    if (form.title) fd.append("title", form.title);
    if (form.description) fd.append("description", form.description);
    fd.append("doc_type", form.doc_type);
    fd.append("source", form.source);
    if (form.tags) fd.append("tags", form.tags);
    if (form.version) fd.append("version", form.version);
    if (form.expiry_date) fd.append("expiry_date", form.expiry_date);
    if (form.jurisdiction) fd.append("jurisdiction", form.jurisdiction);
    if (replacingDoc) fd.append("supersedes_id", replacingDoc.id);

    setBusy(true);
    try {
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(replacingDoc ? `Replaced "${replacingDoc.title}" — old version retired` : "Uploaded — processing in background");
      setOpen(false);
      setReplacingDoc(null);
      setForm({ title: "", description: "", doc_type: "general", source: "superadmin", tags: "", version: "", expiry_date: "", jurisdiction: "" });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
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
    <div className="p-8 max-w-7xl" data-testid="documents-page">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">// Knowledge base</div>
          <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-1">Documents</h1>
          <p className="text-slate-600">Upload, classify and manage the EHS document corpus.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="open-upload-dialog-btn" className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-10">
              <UploadSimple size={16} weight="bold" />
              <span className="ml-2 font-semibold tracking-tight">UPLOAD DOCUMENT</span>
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl rounded-sm border-slate-300">
            <DialogHeader>
              <DialogTitle className="font-bold tracking-tight">Upload EHS Document</DialogTitle>
            </DialogHeader>
            <form onSubmit={upload} className="space-y-4" data-testid="upload-form">
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">File (PDF / DOCX / XLSX / TXT / CSV / MD)</Label>
                <input
                  ref={fileRef}
                  type="file"
                  required
                  accept=".pdf,.docx,.xlsx,.xls,.txt,.csv,.md"
                  data-testid="upload-file-input"
                  className="block w-full text-sm border border-slate-300 rounded-sm file:mr-3 file:py-2 file:px-3 file:bg-slate-900 file:text-white file:border-0 file:font-medium file:cursor-pointer hover:file:bg-slate-800"
                />
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
              <Button
                type="submit"
                disabled={busy}
                data-testid="submit-upload-btn"
                className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-10 font-semibold tracking-tight"
              >
                {busy ? (replacingDoc ? "REPLACING..." : "UPLOADING...") : (replacingDoc ? "UPLOAD REPLACEMENT" : "UPLOAD & PROCESS")}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="border border-slate-300 bg-white overflow-hidden">
        <table className="w-full text-sm">
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
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-700">
      <Hourglass size={11} weight="bold" /> PROCESSING
    </span>
  );
}
