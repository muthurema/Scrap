import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const API = (process.env.REACT_APP_BACKEND_URL || "") + "/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim() || sending) return;
    setSending(true);
    try {
      // Server always returns 200 here to prevent email enumeration;
      // we surface the same UX regardless of whether the address exists.
      await axios.post(`${API}/auth/password-reset/request`, { email: email.trim() });
      setSubmitted(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't request reset link");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">EHS RAG</div>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Forgot password?</h1>
        <p className="text-sm text-slate-600 mb-8 leading-relaxed">
          Enter the email tied to your EHS account. We'll send you a magic link to reset your password — it expires in 15 minutes.
        </p>

        {submitted ? (
          <div className="border border-slate-300 bg-slate-50 p-4 mb-6" data-testid="forgot-success">
            <div className="font-bold tracking-tight text-slate-900 mb-1">Check your inbox</div>
            <div className="text-sm text-slate-700 leading-relaxed">
              If <span className="font-mono">{email}</span> is registered, a magic link is on its way. The link works once and expires in 15 minutes. Didn't get it? Check spam, then try again.
            </div>
            <Button
              type="button"
              onClick={() => { setSubmitted(false); setEmail(""); }}
              variant="outline"
              className="rounded-sm h-9 mt-4 font-mono uppercase text-[11px] tracking-wider"
              data-testid="forgot-resend-btn"
            >
              Send to a different email
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-wider text-slate-500 block mb-1.5">Email</label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                autoComplete="email"
                data-testid="forgot-email-input"
                className="rounded-sm h-10"
              />
            </div>
            <Button
              type="submit"
              disabled={sending}
              data-testid="forgot-submit-btn"
              className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-10 font-semibold tracking-tight w-full"
            >
              {sending ? "Sending…" : "Email me a reset link"}
            </Button>
          </form>
        )}

        <div className="mt-8 border-t border-slate-200 pt-4">
          <Link
            to="/login"
            className="font-mono text-[11px] uppercase tracking-wider text-slate-600 hover:text-slate-900"
            data-testid="forgot-back-to-login"
          >
            ← Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
