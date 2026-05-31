import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import { Copy, Plus, Trash, UsersThree, EnvelopeSimple, Ticket, ShieldCheck } from "@phosphor-icons/react";

export default function TeamPage() {
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const [tab, setTab] = useState("invites");
  const [invites, setInvites] = useState([]);
  const [allowlist, setAllowlist] = useState([]);
  const [members, setMembers] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);

  const [openInvite, setOpenInvite] = useState(false);
  const [openAllow, setOpenAllow] = useState(false);
  const [inviteForm, setInviteForm] = useState({ role: "user", max_uses: 5, expires_in_days: 14, company_id: "" });
  const [allowForm, setAllowForm] = useState({ email: "", role: "user", company_id: "" });
  const [busy, setBusy] = useState(false);
  const [lastCreatedCode, setLastCreatedCode] = useState(null);

  const load = async () => {
    try {
      const [i, a, m, c] = await Promise.all([
        api.get("/team/invites"),
        api.get("/team/allowlist"),
        api.get("/team/members"),
        isSuper ? api.get("/admin/companies") : Promise.resolve({ data: [] }),
      ]);
      setInvites(i.data); setAllowlist(a.data); setMembers(m.data); setCompanies(c.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const createInvite = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { ...inviteForm };
      if (!isSuper) delete payload.company_id;
      const { data } = await api.post("/team/invites", payload);
      setLastCreatedCode(data);
      toast.success(`Invite created: ${data.code}`);
      setInviteForm({ role: "user", max_uses: 5, expires_in_days: 14, company_id: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };

  const revokeInvite = async (id) => {
    if (!confirm("Revoke this invite code?")) return;
    try { await api.delete(`/team/invites/${id}`); toast.success("Revoked"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const addAllowlist = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const url = isSuper && allowForm.company_id ? `/team/allowlist?company_id=${allowForm.company_id}` : "/team/allowlist";
      await api.post(url, { email: allowForm.email, role: allowForm.role });
      toast.success("Added to allowlist");
      setAllowForm({ email: "", role: "user", company_id: "" });
      setOpenAllow(false);
      load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const removeAllowlist = async (id) => {
    if (!confirm("Remove from allowlist?")) return;
    try { await api.delete(`/team/allowlist/${id}`); toast.success("Removed"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const deactivate = async (mid) => {
    if (!confirm("Deactivate this user? They will not be able to log in.")) return;
    try { await api.patch(`/team/members/${mid}/deactivate`); toast.success("Deactivated"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const copy = (text) => navigator.clipboard.writeText(text).then(() => toast.success("Copied"));

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl" data-testid="team-page">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">Team management</div>
      <h1 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 mb-1">Team</h1>
      <p className="text-slate-600 text-sm sm:text-base">
        {isSuper ? "Invite codes & email allowlists across all companies." : "Invite teammates to your org with a shareable code or by allow-listing their email."}
      </p>

      <div className="mt-6 flex gap-px bg-slate-300 border border-slate-300 w-fit">
        {[["invites", "Invite codes", Ticket], ["allowlist", "Email allowlist", EnvelopeSimple], ["members", "Members", UsersThree]].map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`}
            className={`px-4 py-2 font-mono text-[10px] uppercase tracking-wider transition-colors flex items-center gap-2 ${tab === k ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}>
            <Icon size={12} weight="bold" /> {label}
          </button>
        ))}
      </div>

      {loading && <div className="mt-6 font-mono text-xs uppercase tracking-wider text-slate-500">LOADING…</div>}

      {!loading && tab === "invites" && (
        <div className="mt-6">
          <div className="flex justify-between items-end mb-3 gap-3 flex-wrap">
            <div className="text-sm text-slate-600">{invites.length} invite{invites.length === 1 ? "" : "s"}</div>
            <Dialog open={openInvite} onOpenChange={setOpenInvite}>
              <DialogTrigger asChild>
                <Button data-testid="create-invite-btn" className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-9 font-semibold tracking-tight">
                  <Plus size={14} weight="bold" /><span className="ml-1.5">NEW INVITE</span>
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md w-[calc(100%-2rem)] rounded-sm">
                <DialogHeader>
                  <DialogTitle>Create invite code</DialogTitle>
                  <DialogDescription>Share the code with a new teammate. They enter it on sign-up to join your org.</DialogDescription>
                </DialogHeader>
                <form onSubmit={createInvite} className="space-y-4" data-testid="invite-form">
                  <div className="space-y-1.5">
                    <Label className="font-mono text-xs uppercase tracking-wider">Role</Label>
                    <Select value={inviteForm.role} onValueChange={(v) => setInviteForm({ ...inviteForm, role: v })}>
                      <SelectTrigger data-testid="invite-role"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="user">User (chat-only)</SelectItem>
                        {isSuper && <SelectItem value="admin">Admin (org head)</SelectItem>}
                      </SelectContent>
                    </Select>
                  </div>
                  {isSuper && (
                    <div className="space-y-1.5">
                      <Label className="font-mono text-xs uppercase tracking-wider">Company</Label>
                      <Select value={inviteForm.company_id} onValueChange={(v) => setInviteForm({ ...inviteForm, company_id: v })}>
                        <SelectTrigger data-testid="invite-company"><SelectValue placeholder="Pick a company" /></SelectTrigger>
                        <SelectContent>
                          {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="font-mono text-xs uppercase tracking-wider">Max uses</Label>
                      <Input type="number" min={1} max={500} value={inviteForm.max_uses} onChange={(e) => setInviteForm({ ...inviteForm, max_uses: parseInt(e.target.value, 10) })} data-testid="invite-max-uses" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="font-mono text-xs uppercase tracking-wider">Expires (days)</Label>
                      <Input type="number" min={1} max={180} value={inviteForm.expires_in_days} onChange={(e) => setInviteForm({ ...inviteForm, expires_in_days: parseInt(e.target.value, 10) })} data-testid="invite-expires" />
                    </div>
                  </div>
                  <Button type="submit" disabled={busy} data-testid="submit-invite-btn" className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-10 font-semibold tracking-tight">
                    {busy ? "CREATING…" : "GENERATE CODE"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>

          {lastCreatedCode && (
            <div className="border border-emerald-300 bg-emerald-50 p-4 mb-4 flex items-center gap-3" data-testid="last-invite-code">
              <ShieldCheck size={20} weight="bold" className="text-emerald-700 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-emerald-700">New invite created — share this code</div>
                <div className="font-black tracking-widest text-2xl text-slate-900 font-mono">{lastCreatedCode.code}</div>
                <div className="text-xs text-slate-700 mt-0.5">Role: {lastCreatedCode.role} · Company: {lastCreatedCode.company_name} · Expires {new Date(lastCreatedCode.expires_at).toLocaleDateString()}</div>
              </div>
              <Button onClick={() => copy(lastCreatedCode.code)} className="rounded-sm h-9 bg-emerald-700 hover:bg-emerald-800 text-white">
                <Copy size={14} weight="bold" /><span className="ml-1.5">COPY</span>
              </Button>
              <button onClick={() => setLastCreatedCode(null)} className="text-slate-500 hover:text-slate-900" aria-label="Dismiss">×</button>
            </div>
          )}

          <div className="border border-slate-300 bg-white overflow-x-auto">
            <table className="w-full text-sm min-w-[680px]">
              <thead className="bg-slate-100">
                <tr>
                  {["Code", "Role", "Company", "Uses", "Expires", "Status", ""].map((h) => (
                    <th key={h} className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {invites.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-6 text-center text-sm text-slate-500">No invites yet</td></tr>
                )}
                {invites.map((it) => {
                  const expired = new Date(it.expires_at) < new Date();
                  const exhausted = it.uses >= it.max_uses;
                  const active = it.is_active && !expired && !exhausted;
                  return (
                    <tr key={it.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`invite-row-${it.id}`}>
                      <td className="px-3 py-2.5 font-mono font-bold tracking-wider">{it.code}</td>
                      <td className="px-3 py-2.5"><span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 border border-slate-200">{it.role}</span></td>
                      <td className="px-3 py-2.5 text-xs">{it.company_name || "—"}</td>
                      <td className="px-3 py-2.5 font-mono text-xs">{it.uses}/{it.max_uses}</td>
                      <td className="px-3 py-2.5 text-xs">{new Date(it.expires_at).toLocaleDateString()}</td>
                      <td className="px-3 py-2.5">
                        {active ? (
                          <Badge className="rounded-sm bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50 font-mono text-[10px] uppercase">Active</Badge>
                        ) : (
                          <Badge className="rounded-sm bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-100 font-mono text-[10px] uppercase">{expired ? "Expired" : exhausted ? "Used up" : "Revoked"}</Badge>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="inline-flex gap-1">
                          <button onClick={() => copy(it.code)} data-testid={`copy-invite-${it.id}`} title="Copy"
                            className="p-1.5 text-slate-500 hover:text-blue-700 border border-transparent hover:border-blue-200 hover:bg-blue-50"><Copy size={13} /></button>
                          {active && (
                            <button onClick={() => revokeInvite(it.id)} data-testid={`revoke-invite-${it.id}`} title="Revoke"
                              className="p-1.5 text-slate-500 hover:text-rose-700 border border-transparent hover:border-rose-200 hover:bg-rose-50"><Trash size={13} /></button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && tab === "allowlist" && (
        <div className="mt-6">
          <div className="flex justify-between items-end mb-3 gap-3 flex-wrap">
            <div className="text-sm text-slate-600">{allowlist.length} allow-listed email{allowlist.length === 1 ? "" : "s"}</div>
            <Dialog open={openAllow} onOpenChange={setOpenAllow}>
              <DialogTrigger asChild>
                <Button data-testid="add-allowlist-btn" className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-9 font-semibold tracking-tight">
                  <Plus size={14} weight="bold" /><span className="ml-1.5">ADD EMAIL</span>
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md w-[calc(100%-2rem)] rounded-sm">
                <DialogHeader>
                  <DialogTitle>Allow-list an email</DialogTitle>
                  <DialogDescription>Anyone with this exact email can sign up without a code and auto-join your org.</DialogDescription>
                </DialogHeader>
                <form onSubmit={addAllowlist} className="space-y-4">
                  <div className="space-y-1.5">
                    <Label className="font-mono text-xs uppercase tracking-wider">Email</Label>
                    <Input type="email" required value={allowForm.email} onChange={(e) => setAllowForm({ ...allowForm, email: e.target.value })} data-testid="allowlist-email" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="font-mono text-xs uppercase tracking-wider">Role on join</Label>
                    <Select value={allowForm.role} onValueChange={(v) => setAllowForm({ ...allowForm, role: v })}>
                      <SelectTrigger data-testid="allowlist-role"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="user">User</SelectItem>
                        {isSuper && <SelectItem value="admin">Admin</SelectItem>}
                      </SelectContent>
                    </Select>
                  </div>
                  {isSuper && (
                    <div className="space-y-1.5">
                      <Label className="font-mono text-xs uppercase tracking-wider">Company</Label>
                      <Select value={allowForm.company_id} onValueChange={(v) => setAllowForm({ ...allowForm, company_id: v })}>
                        <SelectTrigger data-testid="allowlist-company"><SelectValue placeholder="Pick a company" /></SelectTrigger>
                        <SelectContent>
                          {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <Button type="submit" disabled={busy} className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-10 font-semibold tracking-tight" data-testid="submit-allowlist-btn">
                    {busy ? "ADDING…" : "ALLOW-LIST"}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
          <div className="border border-slate-300 bg-white overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="bg-slate-100">
                <tr>
                  {["Email", "Role", "Company", "Added", "Used", ""].map((h) => (
                    <th key={h} className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allowlist.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">No emails yet</td></tr>
                )}
                {allowlist.map((al) => (
                  <tr key={al.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`allowlist-row-${al.id}`}>
                    <td className="px-3 py-2.5 font-medium">{al.email}</td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[10px] uppercase px-1.5 py-0.5 bg-slate-100 border border-slate-200">{al.role}</span></td>
                    <td className="px-3 py-2.5 text-xs">{al.company_name || "—"}</td>
                    <td className="px-3 py-2.5 text-xs">{new Date(al.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-2.5 text-xs">{al.used_at ? <Badge className="rounded-sm bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50 font-mono text-[10px]">Joined</Badge> : "—"}</td>
                    <td className="px-3 py-2.5 text-right">
                      <button onClick={() => removeAllowlist(al.id)} data-testid={`remove-allowlist-${al.id}`} className="p-1.5 text-slate-500 hover:text-rose-700 border border-transparent hover:border-rose-200 hover:bg-rose-50" title="Remove"><Trash size={13} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && tab === "members" && (
        <div className="mt-6 border border-slate-300 bg-white overflow-x-auto">
          <table className="w-full text-sm min-w-[680px]">
            <thead className="bg-slate-100">
              <tr>
                {["Email", "Name", "Role", "Company", "Joined", "Status", ""].map((h) => (
                  <th key={h} className="text-left px-3 py-2 border-b border-slate-300 font-mono text-[10px] uppercase tracking-wider text-slate-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} className="border-b border-slate-200 last:border-b-0 hover:bg-slate-50" data-testid={`member-row-${m.id}`}>
                  <td className="px-3 py-2.5 font-medium">{m.email}</td>
                  <td className="px-3 py-2.5 text-xs">{m.full_name || "—"}</td>
                  <td className="px-3 py-2.5"><span className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 ${m.role === "superadmin" ? "bg-amber-50 border border-amber-200 text-amber-800" : m.role === "admin" ? "bg-blue-50 border border-blue-200 text-blue-800" : "bg-slate-100 border border-slate-200 text-slate-700"}`}>{m.role}</span></td>
                  <td className="px-3 py-2.5 text-xs">{m.company_id ? (companies.find((c) => c.id === m.company_id)?.name || m.company_id.slice(0, 8)) : "—"}</td>
                  <td className="px-3 py-2.5 text-xs">{new Date(m.created_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2.5">{m.is_active ? <Badge className="rounded-sm bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50 font-mono text-[10px]">Active</Badge> : <Badge className="rounded-sm bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-50 font-mono text-[10px]">Disabled</Badge>}</td>
                  <td className="px-3 py-2.5 text-right">
                    {m.is_active && m.role !== "superadmin" && (
                      <button onClick={() => deactivate(m.id)} data-testid={`deactivate-${m.id}`} className="p-1.5 text-slate-500 hover:text-rose-700 border border-transparent hover:border-rose-200 hover:bg-rose-50" title="Deactivate"><Trash size={13} /></button>
                    )}
                  </td>
                </tr>
              ))}
              {members.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-sm text-slate-500">No members</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
