import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  ChartBar, MagnifyingGlass, Warning, ChatCircle, ThumbsUp, ThumbsDown, Files, Eye,
} from "@phosphor-icons/react";

export default function AnalyticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const { data } = await api.get("/analytics/");
        if (mounted) setData(data);
      } catch (e) {
        console.error(e);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 20_000);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  const maxDay = useMemo(() => Math.max(...(data?.daily_query_counts || []).map((d) => d.count), 1), [data]);

  if (loading && !data) return <div className="p-4 sm:p-8 font-mono text-xs uppercase tracking-wider text-slate-500">LOADING...</div>;

  const fb = data?.feedback_summary || {};

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl" data-testid="analytics-page">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">Query intelligence</div>
      <h1 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 mb-1">Analytics</h1>
      <p className="text-slate-600 text-sm sm:text-base">Last 30 days · what users ask, what works, what doesn't.</p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-slate-200 border border-slate-300 mt-6">
        <Tile icon={ChatCircle} label="Total Queries" value={(data?.daily_query_counts || []).reduce((s, d) => s + d.count, 0)} />
        <Tile icon={ThumbsUp} label="Thumbs Up" value={fb.thumbs_up || 0} accent="emerald" />
        <Tile icon={ThumbsDown} label="Thumbs Down" value={fb.thumbs_down || 0} accent="rose" sublabel={`${fb.pending_review || 0} pending review`} />
        <Tile icon={Warning} label="PII / Injection" value={`${data?.pii_flagged_count || 0} / ${data?.injection_flagged_count || 0}`} sublabel="Flagged inputs" />
      </div>

      <Section title="Daily Query Volume">
        <div className="bg-white border border-slate-300 p-5">
          {data?.daily_query_counts?.length ? (
            <div className="flex items-end gap-1 h-32">
              {data.daily_query_counts.slice(-30).map((d) => (
                <div key={d.date} className="flex-1 flex flex-col items-center group">
                  <div
                    className="w-full bg-blue-600 hover:bg-blue-700 transition-colors min-h-[2px]"
                    style={{ height: `${(d.count / maxDay) * 100}%` }}
                    title={`${d.date}: ${d.count} queries`}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs font-mono uppercase tracking-wider text-slate-500 text-center py-8">No data yet</div>
          )}
        </div>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        <ListBlock
          icon={MagnifyingGlass}
          title="Top Queries"
          subtitle="What people ask most"
          items={data?.top_queries}
          render={(it) => (
            <div className="flex justify-between gap-3">
              <div className="text-sm text-slate-800 truncate flex-1">{it.query}</div>
              <div className="font-mono text-xs text-slate-500">×{it.count}</div>
            </div>
          )}
        />
        <ListBlock
          icon={Warning}
          title="Zero-Result Queries"
          subtitle="Documents may be missing"
          items={data?.zero_result_queries}
          tone="amber"
          render={(it) => (
            <div className="text-sm text-slate-800 truncate">{it.query}</div>
          )}
        />
        <ListBlock
          icon={Eye}
          title="Low-Confidence Queries"
          subtitle="Score below 0.30 — review for gaps"
          items={data?.low_confidence_queries}
          tone="rose"
          render={(it) => (
            <div className="flex justify-between gap-3">
              <div className="text-sm text-slate-800 truncate flex-1">{it.query}</div>
              <div className="font-mono text-xs text-rose-700">{it.score}</div>
            </div>
          )}
        />
        <ListBlock
          icon={Files}
          title="Top Cited Documents"
          subtitle="Most-retrieved sources"
          items={data?.top_cited_docs}
          tone="emerald"
          render={(it) => (
            <div className="flex justify-between gap-3">
              <div className="text-sm text-slate-800 truncate flex-1">{it.title}</div>
              <div className="font-mono text-xs text-emerald-700">×{it.count}</div>
            </div>
          )}
        />
      </div>
    </div>
  );
}

function Tile({ icon: Icon, label, value, sublabel, accent }) {
  const color = { emerald: "text-emerald-700", rose: "text-rose-700", amber: "text-amber-700" }[accent] || "text-slate-900";
  return (
    <div className="bg-white p-5" data-testid={`tile-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
        <Icon size={16} weight="bold" className="text-slate-400" />
      </div>
      <div className={`font-black text-3xl tracking-tighter ${color}`}>{value ?? "—"}</div>
      {sublabel && <div className="text-xs text-slate-500 mt-1">{sublabel}</div>}
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

function ListBlock({ icon: Icon, title, subtitle, items, render, tone }) {
  const accent = { amber: "border-amber-200 bg-amber-50", rose: "border-rose-200 bg-rose-50", emerald: "border-emerald-200 bg-emerald-50" }[tone] || "";
  return (
    <div className="border border-slate-300 bg-white" data-testid={`block-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className={`px-4 py-3 border-b border-slate-300 ${accent}`}>
        <div className="flex items-center gap-2 mb-0.5">
          <Icon size={14} weight="bold" className="text-slate-700" />
          <div className="font-bold tracking-tight text-sm">{title}</div>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">{subtitle}</div>
      </div>
      <div className="divide-y divide-slate-100 max-h-[360px] overflow-y-auto">
        {(items?.length ? items : []).map((it, i) => (
          <div key={i} className="px-4 py-2.5 hover:bg-slate-50 transition-colors">{render(it)}</div>
        ))}
        {!items?.length && (
          <div className="px-4 py-6 text-center font-mono text-[10px] uppercase tracking-wider text-slate-400">No data yet</div>
        )}
      </div>
    </div>
  );
}
