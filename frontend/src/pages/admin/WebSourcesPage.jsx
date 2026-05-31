import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash, ArrowsClockwise, Warning, CheckCircle, Globe } from "@phosphor-icons/react";

const DOC_TYPES = [
  ["general", "General"], ["regulatory", "Regulatory"], ["sop", "SOP / Procedure"],
  ["policy", "Policy"], ["training", "Training"], ["risk_assessment", "Risk / HAZOP"],
];
const SCOPES = [["platform", "Platform (all clients)"], ["client", "Client (your company only)"]];
const FREQS = [["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"]];

export default function WebSourcesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scrapingId, setScrapingId] = useState(null);

  const [form, setForm] = useState({
    url: "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.146",
    label: "OSHA 1910.146 Confined Spaces",
    description: "",
    scope: "platform",
    scrape_frequency: "weekly",
    doc_type: "regulatory",
    crawl_depth: 1,
  });

  const load = async () => {
    try {
      const { data } = await api.get("/web-sources/");
      setItems(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/web-sources/", form);
      toast.success("Web source registered");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const scrape = async (id) => {
    setScrapingId(id);
    try {
      const { data } = await api.post(`/web-sources/${id}/scrape`);
      if (data.error) {
        toast.error("Scrape error: " + data.error);
      } else if (data.changed) {
        toast.success(`Scraped — ${data.chunks_stored} chunks stored`);
      } else {
        toast.info("No content change since last scrape");
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scrape failed");
    } finally {
      setScrapingId(null);
    }
  };

  const remove = async (id) => {
    if (!confirm("Delete this web source and all its chunks?")) return;
    try {
      await api.delete(`/web-sources/${id}`);
      toast.success("Deleted");
      load();
    } catch {
      toast.error("Failed");
    }
  };

  return (
    <div className="p-8 max-w-7xl" data-testid="web-sources-page">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">External knowledge</div>
          <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-1">Web Sources</h1>
          <p className="text-slate-600">URLs scraped and embedded into the knowledge base.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-web-source-btn" className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-10">
              <Plus size={16} weight="bold" />
              <span className="ml-2 font-semibold tracking-tight">ADD URL</span>
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl rounded-sm border-slate-300">
            <DialogHeader><DialogTitle className="font-bold tracking-tight">Add Web Source</DialogTitle></DialogHeader>
            <form onSubmit={create} className="space-y-4" data-testid="web-source-form">
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">URL</Label>
                <Input
                  value={form.url}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                  required
                  className="rounded-sm border-slate-300"
                  data-testid="ws-url"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Label</Label>
                <Input
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                  required
                  className="rounded-sm border-slate-300"
                  data-testid="ws-label"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Scope</Label>
                  <Select value={form.scope} onValueChange={(v) => setForm({ ...form, scope: v })}>
                    <SelectTrigger className="rounded-sm" data-testid="ws-scope"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SCOPES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Frequency</Label>
                  <Select value={form.scrape_frequency} onValueChange={(v) => setForm({ ...form, scrape_frequency: v })}>
                    <SelectTrigger className="rounded-sm" data-testid="ws-frequency"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FREQS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Doc Type</Label>
                  <Select value={form.doc_type} onValueChange={(v) => setForm({ ...form, doc_type: v })}>
                    <SelectTrigger className="rounded-sm" data-testid="ws-doc-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {DOC_TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="font-mono text-xs uppercase tracking-wider">Crawl Depth</Label>
                  <Select value={String(form.crawl_depth)} onValueChange={(v) => setForm({ ...form, crawl_depth: parseInt(v, 10) })}>
                    <SelectTrigger className="rounded-sm" data-testid="ws-depth"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 (page only)</SelectItem>
                      <SelectItem value="2">2 (follow links)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button
                type="submit"
                disabled={busy}
                data-testid="submit-web-source-btn"
                className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-10 font-semibold tracking-tight"
              >
                {busy ? "ADDING..." : "REGISTER URL"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="border border-slate-300 bg-white overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Source</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Scope</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Frequency</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Last Scrape</th>
              <th className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Chunks</th>
              <th className="text-right px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">LOADING...</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">No web sources registered. Add the first URL.</td></tr>
            )}
            {items.map((w) => (
              <tr key={w.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`ws-row-${w.id}`}>
                <td className="px-3 py-2.5 max-w-sm">
                  <div className="font-medium text-slate-900 truncate flex items-center gap-1.5">
                    <Globe size={12} className="text-slate-500" weight="bold" />
                    {w.label}
                  </div>
                  <a href={w.url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 underline truncate block max-w-sm">{w.url}</a>
                </td>
                <td className="px-3 py-2.5">
                  <span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 ${w.scope === "platform" ? "bg-amber-50 border border-amber-200 text-amber-700" : "bg-emerald-50 border border-emerald-200 text-emerald-700"}`}>
                    {w.scope}
                  </span>
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-slate-700 uppercase">{w.scrape_frequency}</td>
                <td className="px-3 py-2.5 text-xs">
                  {w.last_scrape_error ? (
                    <span className="inline-flex items-center gap-1 text-rose-700"><Warning size={11} /> Error</span>
                  ) : w.last_scraped_at ? (
                    new Date(w.last_scraped_at).toLocaleString()
                  ) : (
                    <span className="text-slate-400 font-mono">never</span>
                  )}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-slate-700">{w.last_chunk_count || 0}</td>
                <td className="px-3 py-2.5 text-right">
                  <div className="inline-flex gap-1">
                    <button
                      onClick={() => scrape(w.id)}
                      disabled={scrapingId === w.id}
                      data-testid={`scrape-${w.id}`}
                      title="Scrape now"
                      className="p-1.5 text-slate-500 hover:text-blue-700 border border-transparent hover:border-blue-200 hover:bg-blue-50 transition-colors disabled:opacity-50"
                    >
                      <ArrowsClockwise size={14} weight="bold" className={scrapingId === w.id ? "animate-spin" : ""} />
                    </button>
                    <button
                      onClick={() => remove(w.id)}
                      data-testid={`delete-ws-${w.id}`}
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
