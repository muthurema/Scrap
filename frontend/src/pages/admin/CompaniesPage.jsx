import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Buildings } from "@phosphor-icons/react";

export default function CompaniesPage() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", turnstile_instance_url: "", default_jurisdiction: "" });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try { const { data } = await api.get("/admin/companies"); setItems(data); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const payload = { name: form.name };
      if (form.turnstile_instance_url) payload.turnstile_instance_url = form.turnstile_instance_url;
      if (form.default_jurisdiction) payload.default_jurisdiction = form.default_jurisdiction;
      await api.post("/admin/companies", payload);
      toast.success("Company created");
      setForm({ name: "", turnstile_instance_url: "", default_jurisdiction: "" });
      setOpen(false);
      load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl" data-testid="companies-page">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">Tenant management</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 mb-1">Companies</h1>
          <p className="text-slate-600 text-sm sm:text-base">Each company is its own tenant — its own docs, URLs, users and admins. Superadmin-only.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="add-company-btn" className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-10 self-start sm:self-auto">
              <Plus size={16} weight="bold" /><span className="ml-2 font-semibold tracking-tight">NEW COMPANY</span>
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md w-[calc(100%-2rem)] rounded-sm">
            <DialogHeader>
              <DialogTitle>Create company</DialogTitle>
              <DialogDescription>Adds a tenant. After creating, invite an admin from the Team page.</DialogDescription>
            </DialogHeader>
            <form onSubmit={create} className="space-y-4">
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required data-testid="company-name" />
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Turnstile instance URL (optional)</Label>
                <Input value={form.turnstile_instance_url} onChange={(e) => setForm({ ...form, turnstile_instance_url: e.target.value })} placeholder="https://acme.turnstile360.com" data-testid="company-url" />
              </div>
              <div className="space-y-1.5">
                <Label className="font-mono text-xs uppercase tracking-wider">Default jurisdiction (optional)</Label>
                <Input value={form.default_jurisdiction} onChange={(e) => setForm({ ...form, default_jurisdiction: e.target.value })} placeholder="US, UK, EU…" data-testid="company-jurisdiction" />
              </div>
              <Button type="submit" disabled={busy} data-testid="submit-company-btn" className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-10 font-semibold tracking-tight">
                {busy ? "CREATING…" : "CREATE COMPANY"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="border border-slate-300 bg-white overflow-x-auto">
        <table className="w-full text-sm min-w-[560px]">
          <thead className="bg-slate-100">
            <tr>
              {["Name", "Turnstile URL", "Default juris.", "Created", "Status"].map((h) => (
                <th key={h} className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="px-3 py-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">LOADING…</td></tr>}
            {!loading && items.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-sm text-slate-500">
                <Buildings size={24} className="mx-auto text-slate-400 mb-2" />
                No companies yet. Create one to start onboarding org admins.
              </td></tr>
            )}
            {items.map((c) => (
              <tr key={c.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`company-row-${c.id}`}>
                <td className="px-3 py-2.5 font-medium text-slate-900">{c.name}</td>
                <td className="px-3 py-2.5 text-xs text-blue-700 truncate max-w-xs"><a href={c.turnstile_instance_url || "#"} target="_blank" rel="noreferrer" className="underline">{c.turnstile_instance_url || "—"}</a></td>
                <td className="px-3 py-2.5 font-mono text-xs">{c.default_jurisdiction || "—"}</td>
                <td className="px-3 py-2.5 text-xs">{new Date(c.created_at).toLocaleDateString()}</td>
                <td className="px-3 py-2.5"><span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 ${c.is_active ? "bg-emerald-50 border border-emerald-200 text-emerald-700" : "bg-slate-100 border border-slate-200 text-slate-500"}`}>{c.is_active ? "Active" : "Inactive"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
