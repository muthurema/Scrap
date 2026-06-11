import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ArrowRight, CheckCircle, Ticket } from "@phosphor-icons/react";
import { Logo } from "@/components/Logo";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [inviteInfo, setInviteInfo] = useState(null); // { valid, role, company_name }
  const [busy, setBusy] = useState(false);

  // Lookup the company name as the user types the invite code (debounced)
  useEffect(() => {
    if (mode !== "register" || !inviteCode || inviteCode.length < 6) {
      setInviteInfo(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/auth/lookup-company?code=${encodeURIComponent(inviteCode.trim().toUpperCase())}`);
        setInviteInfo(data);
      } catch {
        setInviteInfo({ valid: false });
      }
    }, 300);
    return () => clearTimeout(t);
  }, [inviteCode, mode]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const user = mode === "login"
        ? await login(email, password)
        : await register({
            email, password, full_name: fullName, role: "user",
            invite_code: inviteCode ? inviteCode.trim().toUpperCase() : undefined,
          });
      toast.success(`Welcome, ${user.full_name || user.email}`);
      navigate(["superadmin", "admin"].includes(user.role) ? "/admin/stats" : "/chat");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail[0]?.msg : "Authentication failed");
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* LEFT — Brand */}
      <div
        className="hidden lg:flex flex-col w-[44%] bg-slate-900 text-white p-12 relative overflow-hidden"
        data-testid="login-brand-panel"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/40 via-slate-900/60 to-slate-900/90"></div>
        <div className="relative z-10 flex items-center gap-3">
          <Logo size={40} />
          <div>
            <div className="font-mono text-xs uppercase tracking-[0.25em] text-white/60">CIDSA</div>
            <div className="font-bold text-lg tracking-tight">GIS KNOWLEDGE ASSISTANT</div>
          </div>
        </div>

        <div className="relative z-10 mt-auto">
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-white/60 mb-3">AI co-pilot for geospatial teams</div>
          <h1 className="text-5xl font-black tracking-tighter leading-[0.95] mb-6">
            Answers grounded in <span className="text-emerald-400">your</span> GIS books.
          </h1>
          <p className="text-white/70 text-base max-w-md leading-relaxed">
            Coordinate systems, projections, spatial analysis, remote sensing, cartography and PostGIS — retrieve, cite and reason across your geospatial reference library, with every answer attributed to its book and author.
          </p>

          <div className="mt-10 grid grid-cols-3 gap-px bg-white/10 border border-white/10 max-w-md">
            {[
              { label: "Cited", value: "Book + Author" },
              { label: "Search", value: "Hybrid RAG" },
              { label: "Vision", value: "Map Analysis" },
            ].map((x) => (
              <div key={x.label} className="bg-slate-900/80 p-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/50">{x.label}</div>
                <div className="font-bold text-base mt-1">{x.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT — Form */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-8 bg-slate-50">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-8 flex items-center gap-3">
            <Logo size={36} />
            <div className="font-bold text-lg tracking-tight">CIDSA RAG</div>
          </div>

          <div className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500 mb-2">
            {mode === "login" ? "Sign in" : "Create account"}
          </div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tighter text-slate-900 mb-2">
            {mode === "login" ? "Sign in to continue" : "Get started"}
          </h2>
          <p className="text-slate-600 text-sm mb-8">
            {mode === "login"
              ? "Enter your credentials to access the GIS knowledge base."
              : "Have an invite code from your admin? Drop it in below — otherwise your email must be allow-listed."}
          </p>

          <form onSubmit={submit} className="space-y-5">
            {mode === "register" && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="full-name" className="font-mono text-xs uppercase tracking-wider text-slate-700">Full name</Label>
                  <Input
                    id="full-name"
                    data-testid="register-fullname-input"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                    className="rounded-sm border-slate-300 focus-visible:ring-emerald-600"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="invite-code" className="font-mono text-xs uppercase tracking-wider text-slate-700">Invite code <span className="normal-case lowercase text-slate-400">(optional)</span></Label>
                  <div className="relative">
                    <Ticket size={14} weight="bold" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                      id="invite-code"
                      data-testid="register-invite-input"
                      type="text"
                      value={inviteCode}
                      onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                      placeholder="ABCD1234"
                      maxLength={16}
                      autoComplete="off"
                      className="rounded-sm border-slate-300 focus-visible:ring-emerald-600 pl-9 font-mono tracking-widest"
                    />
                  </div>
                  {inviteInfo && inviteInfo.valid && (
                    <div className="flex items-center gap-2 text-xs text-emerald-700 font-medium" data-testid="invite-valid">
                      <CheckCircle size={14} weight="fill" />
                      Joining <span className="font-bold">{inviteInfo.company_name || "company"}</span> as <span className="font-bold">{inviteInfo.role}</span>
                    </div>
                  )}
                  {inviteCode && inviteInfo && !inviteInfo.valid && (
                    <div className="text-xs text-rose-700 font-medium" data-testid="invite-invalid">
                      Code not recognised, expired, or fully used.
                    </div>
                  )}
                </div>
              </>
            )}
            <div className="space-y-2">
              <Label htmlFor="email" className="font-mono text-xs uppercase tracking-wider text-slate-700">Email</Label>
              <Input
                id="email"
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="rounded-sm border-slate-300 focus-visible:ring-emerald-600"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="font-mono text-xs uppercase tracking-wider text-slate-700">Password</Label>
                {mode === "login" && (
                  <Link
                    to="/forgot-password"
                    data-testid="login-forgot-link"
                    className="font-mono text-[10px] uppercase tracking-wider text-slate-500 hover:text-emerald-700"
                  >
                    Forgot?
                  </Link>
                )}
              </div>
              <Input
                id="password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="rounded-sm border-slate-300 focus-visible:ring-emerald-600"
              />
            </div>
            <Button
              type="submit"
              data-testid="login-submit-button"
              disabled={busy}
              className="w-full rounded-sm bg-emerald-600 hover:bg-emerald-700 text-white font-semibold tracking-tight h-11 group"
            >
              {busy
                ? (mode === "login" ? "SIGNING IN..." : "CREATING...")
                : (
                  <span className="flex items-center justify-center gap-2">
                    {mode === "login" ? "SIGN IN" : "CREATE ACCOUNT"}
                    <ArrowRight size={18} weight="bold" className="group-hover:translate-x-0.5 transition-transform" />
                  </span>
                )}
            </Button>
          </form>

          <div className="mt-6 text-sm text-slate-600">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button
                  data-testid="switch-to-register-btn"
                  className="text-emerald-600 hover:text-emerald-800 font-medium underline-offset-2 hover:underline"
                  onClick={() => setMode("register")}
                >
                  Register
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  data-testid="switch-to-login-btn"
                  className="text-emerald-600 hover:text-emerald-800 font-medium underline-offset-2 hover:underline"
                  onClick={() => setMode("login")}
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
