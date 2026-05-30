import { useEffect, useState, Fragment } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { SealCheck, DownloadSimple, Warning, MagnifyingGlass } from "@phosphor-icons/react";

export default function AcknowledgementsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/acknowledgements/?high_risk_only=${highRiskOnly}&limit=200`);
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [highRiskOnly]);

  const downloadCSV = async () => {
    try {
      const token = localStorage.getItem("ehs_token");
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/acknowledgements/export/csv?high_risk_only=${highRiskOnly}`;
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `ehs-acknowledgements-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      toast.success("CSV downloaded");
    } catch (e) {
      toast.error("Download failed");
    }
  };

  return (
    <div className="p-8 max-w-7xl" data-testid="acknowledgements-page">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">// Compliance audit trail</div>
          <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-1">Acknowledgements</h1>
          <p className="text-slate-600">Immutable evidence that workers read and accepted EHS guidance. Exportable for regulatory audit.</p>
        </div>
        <div className="flex gap-2">
          <div className="flex gap-px bg-slate-300 border border-slate-300">
            <button
              onClick={() => setHighRiskOnly(false)}
              data-testid="filter-all-acks"
              className={`px-4 py-2 font-mono text-[10px] uppercase tracking-wider transition-colors ${!highRiskOnly ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}
            >
              All
            </button>
            <button
              onClick={() => setHighRiskOnly(true)}
              data-testid="filter-highrisk-acks"
              className={`px-4 py-2 font-mono text-[10px] uppercase tracking-wider transition-colors ${highRiskOnly ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}
            >
              High-Risk Only
            </button>
          </div>
          <Button
            onClick={downloadCSV}
            data-testid="export-csv-btn"
            className="rounded-sm bg-emerald-700 hover:bg-emerald-800 text-white h-10 font-semibold tracking-tight"
          >
            <DownloadSimple size={16} weight="bold" />
            <span className="ml-2">EXPORT CSV</span>
          </Button>
        </div>
      </div>

      <div className="mb-3 font-mono text-xs uppercase tracking-wider text-slate-600">
        {total} acknowledgement{total === 1 ? "" : "s"}
      </div>

      {loading && items.length === 0 ? (
        <div className="text-xs font-mono uppercase tracking-wider text-slate-500">LOADING...</div>
      ) : items.length === 0 ? (
        <div className="border border-slate-300 bg-white p-12 text-center">
          <SealCheck size={32} weight="bold" className="text-slate-400 mx-auto mb-3" />
          <div className="font-bold text-lg text-slate-900 mb-1">No acknowledgements yet</div>
          <div className="text-sm text-slate-600">
            Workers haven't acknowledged any answers. The "I understand" button appears under every chat reply.
          </div>
        </div>
      ) : (
        <div className="border border-slate-300 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-100">
              <tr>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">When</th>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">User</th>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Site / Role</th>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Juris.</th>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Risk</th>
                <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Query</th>
                <th className="text-right px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Detail</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <Fragment key={it.id}>
                  <tr className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`ack-row-${it.id}`}>
                    <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                      {(typeof it.created_at === "string" ? it.created_at : new Date(it.created_at).toISOString()).slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium truncate max-w-[160px]">{it.user_full_name || it.user_email}</div>
                      <div className="font-mono text-[10px] text-slate-500 truncate max-w-[160px]">{it.user_email}</div>
                    </td>
                    <td className="px-3 py-2.5 text-xs">
                      <div className="text-slate-800 truncate max-w-[140px]">{it.user_site || "—"}</div>
                      <div className="text-slate-500 truncate max-w-[140px]">{it.user_role_label || "—"}</div>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs">
                      {it.user_jurisdiction ? (
                        <span className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-800 text-[10px] uppercase tracking-wider">{it.user_jurisdiction}</span>
                      ) : "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      {it.is_high_risk ? (
                        <Badge className="rounded-sm bg-rose-50 text-rose-800 border border-rose-300 hover:bg-rose-50 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0">
                          <Warning size={10} weight="bold" className="mr-0.5" /> High
                        </Badge>
                      ) : (
                        <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">normal</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 max-w-md">
                      <div className="text-xs text-slate-700 truncate">{it.user_query || "—"}</div>
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => setExpanded(expanded === it.id ? null : it.id)}
                        data-testid={`expand-ack-${it.id}`}
                        className="font-mono text-[10px] uppercase tracking-wider px-2 py-1 border border-slate-300 hover:bg-slate-100 text-slate-700"
                      >
                        {expanded === it.id ? "Hide" : "View"}
                      </button>
                    </td>
                  </tr>
                  {expanded === it.id && (
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <td colSpan={7} className="p-4">
                        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">Answer snapshot (immutable)</div>
                        <div className="text-sm text-slate-800 bg-white border border-slate-200 p-3 rounded-sm whitespace-pre-wrap max-h-72 overflow-y-auto">{it.answer_snapshot || "—"}</div>
                        {(it.sources_snapshot || []).length > 0 && (
                          <>
                            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mt-3 mb-1">Source titles at moment of ack</div>
                            <div className="flex flex-wrap gap-1">
                              {it.sources_snapshot.map((s, i) => (
                                <span key={i} className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-white border border-slate-200 text-slate-700">[{i + 1}] {(s.title || "").slice(0, 50)}</span>
                              ))}
                            </div>
                          </>
                        )}
                        <div className="grid grid-cols-2 gap-4 mt-3 text-xs text-slate-600">
                          <div><span className="font-mono uppercase tracking-wider text-slate-500">Confidence:</span> {typeof it.confidence_snapshot === "number" ? (it.confidence_snapshot * 100).toFixed(0) + "%" : "—"}</div>
                          <div><span className="font-mono uppercase tracking-wider text-slate-500">IP:</span> {it.ip || "—"}</div>
                          <div><span className="font-mono uppercase tracking-wider text-slate-500">Industry:</span> {it.user_industry || "—"}</div>
                          <div><span className="font-mono uppercase tracking-wider text-slate-500">Ack ID:</span> <span className="font-mono">{it.id?.slice(0, 8)}</span></div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
