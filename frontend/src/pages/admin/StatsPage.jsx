import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  ChartBar, FileText, Database, Globe, ChatCircle, Users, Warning, CheckCircle,
  ClockCounterClockwise, ShieldCheck,
} from "@phosphor-icons/react";

export default function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [audit, setAudit] = useState([]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const [statsR, auditR] = await Promise.all([
          api.get("/admin/stats"),
          api.get("/audit/?limit=15").catch(() => ({ data: { items: [] } })),
        ]);
        if (mounted) {
          setStats(statsR.data);
          setAudit(auditR.data.items || []);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 10_000);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  return (
    <div className="p-8 max-w-7xl" data-testid="stats-page">
      <Header />

      {loading && !stats ? (
        <div className="font-mono text-xs uppercase tracking-[0.2em] text-slate-500 mt-8">LOADING STATS...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-slate-200 border border-slate-300 mt-6" data-testid="stats-grid">
            <Stat icon={FileText} label="Documents" value={stats?.total_documents} sublabel={`${stats?.company_doc_count ?? 0} company · ${stats?.base_corpus_count ?? 0} base`} />
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

          <Section title="Knowledge Source Priority">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-slate-200 border border-slate-300">
              {[
                { label: "Company Uploads", boost: "1.5×", color: "bg-blue-600", desc: "Documents uploaded by superadmins" },
                { label: "Turnstile DMS Sync", boost: "1.3×", color: "bg-indigo-600", desc: "Synced from Turnstile360 (stub)" },
                { label: "Base EHS Corpus", boost: "1.0×", color: "bg-slate-700", desc: "Platform-wide standards (OSHA, ISO)" },
              ].map((s) => (
                <div key={s.label} className="bg-white p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <span className={`w-2 h-2 ${s.color} inline-block`}></span>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Priority Boost</div>
                  </div>
                  <div className="font-black text-3xl tracking-tight text-slate-900 mb-1">{s.boost}</div>
                  <div className="font-semibold text-sm text-slate-800 mb-1">{s.label}</div>
                  <div className="text-xs text-slate-600">{s.desc}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Document-Type Chunking Strategy">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 border border-slate-300 overflow-hidden">
                <table className="w-full text-sm">
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
                      ["SOPs / Procedures", "512", "100", "1.2×"],
                      ["Regulatory (ISO/OSHA)", "768", "150", "1.0×"],
                      ["Incident Reports", "256", "50", "1.1×"],
                      ["HAZOP / Risk", "512", "128", "1.3×"],
                      ["Training Materials", "384", "75", "1.0×"],
                      ["Permits / Compliance", "512", "100", "1.1×"],
                      ["Policies", "512", "100", "1.4×"],
                      ["MSDS / SDS", "384", "64", "1.2×"],
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
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">// System overview</div>
      <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-1">Control Room</h1>
      <p className="text-slate-600">Real-time stats across the EHS knowledge graph.</p>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-10">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">// {title.toLowerCase()}</div>
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
};

function AuditWidget({ items }) {
  return (
    <div className="border border-slate-300 bg-white flex flex-col" data-testid="audit-widget">
      <div className="px-3 py-2 bg-slate-100 border-b border-slate-300 flex items-center gap-2">
        <ShieldCheck size={14} weight="bold" className="text-slate-700" />
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600 flex-1">// Recent admin activity</div>
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
