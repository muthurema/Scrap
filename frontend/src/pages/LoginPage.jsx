import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ShieldCheck, ArrowRight } from "@phosphor-icons/react";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("admin@ehsrag.com");
  const [password, setPassword] = useState("Admin@12345");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const user = mode === "login"
        ? await login(email, password)
        : await register({ email, password, full_name: fullName, role: "user" });
      toast.success(`Welcome, ${user.full_name || user.email}`);
      navigate(user.role === "superadmin" ? "/admin/stats" : "/chat");
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
        style={{
          backgroundImage: "url('https://static.prod-images.emergentagent.com/jobs/0e7c1b13-1b55-4366-b1aa-0aee4d1bbb0f/images/dc67fb641583c3295298187cf006e27b9b92ed9f39f3b50e729eb4bc88cdecda.png')",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
        data-testid="login-brand-panel"
      >
        <div className="absolute inset-0 bg-slate-900/75"></div>
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-9 h-9 border border-white/40 flex items-center justify-center">
            <ShieldCheck size={20} weight="bold" />
          </div>
          <div>
            <div className="font-mono text-xs uppercase tracking-[0.25em] text-white/60">Turnstile360</div>
            <div className="font-bold text-lg tracking-tight">EHS INTELLIGENCE</div>
          </div>
        </div>

        <div className="relative z-10 mt-auto">
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-white/60 mb-3">// AI co-pilot for safety teams</div>
          <h1 className="text-5xl font-black tracking-tighter leading-[0.95] mb-6">
            Answers grounded in <span className="text-blue-400">your</span> EHS documents.
          </h1>
          <p className="text-white/70 text-base max-w-md leading-relaxed">
            Permits, HAZOPs, SOPs, incident reports, ISO 45001 and OSHA — retrieve, cite and reason across your entire safety knowledge base.
          </p>

          <div className="mt-10 grid grid-cols-3 gap-px bg-white/10 border border-white/10 max-w-md">
            {[
              { label: "Company Docs", boost: "1.5×" },
              { label: "Turnstile DMS", boost: "1.3×" },
              { label: "Base Corpus", boost: "1.0×" },
            ].map((x) => (
              <div key={x.label} className="bg-slate-900/80 p-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/50">Priority</div>
                <div className="font-black text-2xl mt-1">{x.boost}</div>
                <div className="text-xs text-white/70 mt-1">{x.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT — Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-8 flex items-center gap-3">
            <div className="w-9 h-9 border border-slate-300 flex items-center justify-center">
              <ShieldCheck size={20} weight="bold" className="text-slate-900" />
            </div>
            <div className="font-bold text-lg tracking-tight">EHS INTELLIGENCE</div>
          </div>

          <div className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500 mb-2">
            {mode === "login" ? "// Authenticate" : "// Create account"}
          </div>
          <h2 className="text-3xl font-black tracking-tighter text-slate-900 mb-2">
            {mode === "login" ? "Sign in to continue" : "Get started"}
          </h2>
          <p className="text-slate-600 text-sm mb-8">
            {mode === "login"
              ? "Enter your credentials to access the EHS knowledge base."
              : "Create a new account. The first registered user becomes superadmin."}
          </p>

          <form onSubmit={submit} className="space-y-5">
            {mode === "register" && (
              <div className="space-y-2">
                <Label htmlFor="full-name" className="font-mono text-xs uppercase tracking-wider text-slate-700">Full name</Label>
                <Input
                  id="full-name"
                  data-testid="register-fullname-input"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  className="rounded-sm border-slate-300 focus-visible:ring-blue-600"
                />
              </div>
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
                className="rounded-sm border-slate-300 focus-visible:ring-blue-600"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="font-mono text-xs uppercase tracking-wider text-slate-700">Password</Label>
              <Input
                id="password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="rounded-sm border-slate-300 focus-visible:ring-blue-600"
              />
            </div>
            <Button
              type="submit"
              data-testid="login-submit-button"
              disabled={busy}
              className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold tracking-tight h-11 group"
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
                  className="text-blue-600 hover:text-blue-800 font-medium underline-offset-2 hover:underline"
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
                  className="text-blue-600 hover:text-blue-800 font-medium underline-offset-2 hover:underline"
                  onClick={() => setMode("login")}
                >
                  Sign in
                </button>
              </>
            )}
          </div>

          {mode === "login" && (
            <div className="mt-10 border-t border-slate-200 pt-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 mb-2">// Demo credentials</div>
              <div className="font-mono text-xs text-slate-600 space-y-0.5">
                <div>admin@ehsrag.com</div>
                <div>Admin@12345</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
