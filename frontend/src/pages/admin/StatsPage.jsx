import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  ChartBar, FileText, Database, Globe, ChatCircle, Users, Warning, CheckCircle,
  ClockCounterClockwise, ShieldCheck, ArrowsClockwise,
} from "@phosphor-icons/react";

export default function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [audit, setAudit] = useState([]);
  const [reseedBusy, setReseedBusy] = useState(false);

  const load = async () => {
    try {
      const [statsR, auditR] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/audit/?limit=15").catch(() => ({ data: { items: [] } })),
      ]);
      setStats(statsR.data);
      setAudit(auditR.data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    const tick = async () => { if (mounted) await load(); };
    tick();
    const t = setInterval(tick, 10_000);
    return () => { mounted = false; clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reseed = async (force) => {
    const label = force ? "FORCE re-seed" : "re-seed";
    const msg = force
      ? "FORCE re-seed will DELETE all existing base-corpus documents and re-ingest from scratch. Continue?"
      : "Re-seed the base GIS corpus? Existing titles will be skipped (safe to run anytime).";
    if (!confirm(msg)) return;
    setReseedBusy(true);
    const t = toast.loading(`${label} in progress — embedding chunks…`);
    try {
      const { data } = await api.post(`/admin/reseed-corpus?force=${force}`);
      toast.dismiss(t);
      const detail = `${data.created} created · ${data.skipped} skipped · ${data.failed} failed · ${data.total_chunks} chunks`;
      if (data.failed > 0) toast.warning(detail);
      else toast.success(detail);
      load();
    } catch (e) {
      toast.dismiss(t);
      toast.error(e?.response?.data?.detail || "Re-seed failed");
    } finally {
      setReseedBusy(false);
    }
  };

  const resetQdrant = async (collection) => {
    const label = collection === "ehs_base_knowledge" ? "base knowledge" : "company docs";
    const msg = `Wipe and recreate the "${label}" Qdrant collection?\n\n` +
      "Use this ONLY if you're seeing 'operands could not be broadcast' " +
      "errors in the backend logs (index corruption from interrupted writes).\n\n" +
      "All chunks in this collection will be deleted. You'll need to re-upload " +
      "the documents (or use Force Re-seed for the base corpus).";
    if (!confirm(msg)) return;
    setReseedBusy(true);
    const t = toast.loading(`Resetting ${label} collection…`);
    try {
      const { data } = await api.post(
        `/admin/qdrant/reset?collection=${encodeURIComponent(collection)}&confirm=true`,
      );
      toast.dismiss(t);
      toast.success(
        `Collection wiped. ${data.documents_invalidated} document(s) marked for re-upload.`,
      );
      load();
    } catch (e) {
      toast.dismiss(t);
      toast.error(e?.response?.data?.detail || "Qdrant reset failed");
    } finally {
      setReseedBusy(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl" data-testid="stats-page">
      <Header />

      {loading && !stats ? (
        <div className="font-mono text-xs uppercase tracking-[0.2em] text-slate-500 mt-8">LOADING STATS...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-px bg-slate-200 border border-slate-300 mt-6" data-testid="stats-grid">
            <Stat icon={FileText} label="Documents" value={stats?.total_documents} sublabel="GIS books in library" />
            <Stat icon={Database} label="Chunks Embedded" value={stats?.total_chunks_embedded} sublabel="In vector store" />
            <Stat icon={ChatCircle} label="Chat Sessions" value={stats?.total_chat_sessions} sublabel={`${stats?.total_messages ?? 0} messages`} />
            <Stat icon={Users} label="Users" value={stats?.total_users} sublabel="Total registered" />
            <Stat icon={Globe} label="Web Sources" value={stats?.total_web_sources} sublabel="URLs tracked" />
            <Stat
              icon={Warning}
              label="Pending Review"
              value={stats?.web_sources_pending_review}
              sublabel="Significant changes"
              accent={stats?.web_sources_pending_review > 0 ? "amber" : null}
            />
            <Stat
              icon={stats?.qdrant_status === "healthy" ? CheckCircle : Warning}
              label="Qdrant"
              value={stats?.qdrant_status === "healthy" ? "OK" : (stats?.qdrant_status || "?")}
              sublabel="Vector database"
              accent={stats?.qdrant_status === "healthy" ? "emerald" : "amber"}
            />
            <Stat icon={ChartBar} label="System" value="LIVE" sublabel="Auto-refresh 10s" accent="emerald" />
          </div>

          <Section title="Knowledge Base">
            <CorpusHealth stats={stats} onReseed={reseed} onResetQdrant={resetQdrant} busy={reseedBusy} />
          </Section>

          <Section title="Document-Type Chunking Strategy">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 border border-slate-300 overflow-hidden">
                <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[480px]">
                  <thead>
                    <tr className="bg-slate-100">
                      <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Type</th>
                      <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Chunk Size</th>
                      <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Overlap</th>
                      <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Type Boost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["Books / Guides / Manuals", "512", "100", "1.2×"],
                      ["Standards / Specs", "768", "150", "1.0×"],
                      ["Technical Analysis", "512", "128", "1.3×"],
                      ["Tutorials", "384", "75", "1.0×"],
                      ["General Reference", "512", "100", "1.0×"],
                    ].map(([t, cs, co, b]) => (
                      <tr key={t} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium">{t}</td>
                        <td className="px-3 py-2 font-mono text-xs">{cs}</td>
                        <td className="px-3 py-2 font-mono text-xs">{co}</td>
                        <td className="px-3 py-2 font-mono text-xs text-blue-700">{b}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>
              <AuditWidget items={audit} />
            </div>
          </Section>
        </>
      )}
    </div>
  );
}

function Header() {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">System overview</div>
      <h1 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 mb-1">Control Room</h1>
      <p className="text-slate-600 text-sm sm:text-base">Real-time stats across the GIS knowledge base.</p>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-10">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">{title.toLowerCase()}</div>
      <h2 className="text-xl font-bold tracking-tight text-slate-900 mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Stat({ icon: Icon, label, value, sublabel, accent }) {
  const accentColors = {
    emerald: "text-emerald-700",
    amber: "text-amber-700",
    rose: "text-rose-700",
  };
  const valueColor = accent ? accentColors[accent] : "text-slate-900";
  return (
    <div className="bg-white p-5" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
        <Icon size={16} className="text-slate-400" weight="bold" />
      </div>
      <div className={`font-black text-3xl tracking-tighter ${valueColor}`}>
        {value ?? "—"}
      </div>
      <div className="text-xs text-slate-500 mt-1">{sublabel}</div>
    </div>
  );
}

const ACTION_LABELS = {
  upload_document: "Upload",
  delete_document: "Delete doc",
  reprocess_document: "Reprocess",
  create_web_source: "Add URL",
  delete_web_source: "Remove URL",
  scrape_web_source: "Scrape",
  acknowledge_change: "Ack change",
  delete_chat_session: "Delete chat",
  delete_all_chat_sessions: "Clear chats",
  delete_chat_message: "Delete msg",
  reseed_base_corpus: "Re-seed",
};

function CorpusHealth({ stats, onReseed, onResetQdrant, busy }) {
  const chunks = stats?.total_chunks_embedded ?? 0;
  const baseDocs = stats?.base_corpus_count ?? 0;
  const empty = chunks === 0;
  return (
    <div
      className={`border p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4 ${
        empty
          ? "bg-amber-50 border-amber-300"
          : "bg-white border-slate-300"
      }`}
      data-testid="corpus-health"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {empty ? (
            <Warning size={16} weight="bold" className="text-amber-700" />
          ) : (
            <CheckCircle size={16} weight="bold" className="text-emerald-700" />
          )}
          <div className="font-bold tracking-tight text-slate-900">
            {empty ? "Knowledge base is empty — chat won't return sources yet" : "Knowledge base healthy"}
          </div>
        </div>
        <div className="text-xs text-slate-600 leading-relaxed">
          {empty
            ? "Go to Documents and upload your GIS reference books (PDF / DOCX / TXT). Once they finish processing, the assistant will cite them by book and author."
            : <>
                <span className="font-mono">{chunks}</span> embedded chunks across <span className="font-mono">{baseDocs}</span> books. Use the index-reset tools only if you see vector-store errors in the logs.
              </>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 shrink-0">
        {onResetQdrant && (
          <>
            <Button
              onClick={() => onResetQdrant("ehs_base_knowledge")}
              disabled={busy}
              data-testid="qdrant-reset-base-btn"
              variant="outline"
              className="rounded-sm border-rose-400 text-rose-700 hover:bg-rose-50 h-9 font-mono uppercase text-[11px] tracking-wider"
              title="Wipe & recreate the knowledge-base Qdrant collection (use only if you see vector-store errors in logs)"
            >
              Reset Index
            </Button>
            <Button
              onClick={() => onResetQdrant("ehs_company_docs")}
              disabled={busy}
              data-testid="qdrant-reset-company-btn"
              variant="outline"
              className="rounded-sm border-rose-400 text-rose-700 hover:bg-rose-50 h-9 font-mono uppercase text-[11px] tracking-wider"
              title="Wipe & recreate the secondary Qdrant collection"
            >
              Reset Index (2)
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function AuditWidget({ items }) {
  return (
    <div className="border border-slate-300 bg-white flex flex-col" data-testid="audit-widget">
      <div className="px-3 py-2 bg-slate-100 border-b border-slate-300 flex items-center gap-2">
        <ShieldCheck size={14} weight="bold" className="text-slate-700" />
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600 flex-1">Recent admin activity</div>
        <ClockCounterClockwise size={11} className="text-slate-400" />
      </div>
      <div className="flex-1 max-h-[420px] overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-3 py-6 text-center font-mono text-[10px] uppercase tracking-wider text-slate-400">
            No admin actions yet
          </div>
        ) : items.map((it, i) => (
          <div key={it.id || i} className="px-3 py-2 border-b border-slate-100 last:border-b-0 hover:bg-slate-50" data-testid={`audit-${i}`}>
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-700">
                {ACTION_LABELS[it.action] || it.action}
              </span>
              <span className="text-[10px] font-mono text-slate-500">{(it.created_at || "").slice(11, 19)}</span>
            </div>
            <div className="text-xs text-slate-700 mt-1 truncate">
              {it.user_email}
              {it.details?.title && <span className="text-slate-500"> · {it.details.title}</span>}
              {it.details?.url && <span className="text-slate-500"> · {it.details.url.slice(0, 40)}{it.details.url.length > 40 ? "…" : ""}</span>}
              {it.details?.filename && <span className="text-slate-500"> · {it.details.filename}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
