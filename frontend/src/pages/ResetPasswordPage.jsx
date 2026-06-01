import { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const API = (process.env.REACT_APP_BACKEND_URL || "") + "/api";

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";

  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [linkError, setLinkError] = useState("");

  useEffect(() => {
    if (!token) {
      setLinkError("This reset link is missing its security token. Request a new one.");
    }
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    if (pw.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (pw !== pw2) {
      toast.error("Passwords don't match");
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/auth/password-reset/confirm`, { token, new_password: pw });
      setDone(true);
      // Auto-redirect to login after 3s so users land on the sign-in page
      // without having to hunt for the link.
      setTimeout(() => navigate("/login"), 3000);
    } catch (e) {
      const detail = e?.response?.data?.detail || "Reset failed";
      setLinkError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">EHS RAG</div>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Set a new password</h1>

        {done ? (
          <div className="border border-emerald-200 bg-emerald-50 p-4 mb-6" data-testid="reset-success">
            <div className="font-bold tracking-tight text-emerald-900 mb-1">Password updated</div>
            <div className="text-sm text-emerald-800 leading-relaxed">
              Your password has been changed. Redirecting you to sign in…
            </div>
            <Link
              to="/login"
              className="font-mono text-[11px] uppercase tracking-wider text-emerald-900 hover:underline mt-3 inline-block"
              data-testid="reset-go-login"
            >
              Go to sign in →
            </Link>
          </div>
        ) : linkError ? (
          <div className="border border-rose-200 bg-rose-50 p-4 mb-6" data-testid="reset-link-error">
            <div className="font-bold tracking-tight text-rose-900 mb-1">Reset link problem</div>
            <div className="text-sm text-rose-800 leading-relaxed mb-3">{linkError}</div>
            <Link
              to="/forgot-password"
              className="font-mono text-[11px] uppercase tracking-wider text-rose-900 hover:underline"
              data-testid="reset-request-new"
            >
              Request a new link →
            </Link>
          </div>
        ) : (
          <>
            <p className="text-sm text-slate-600 mb-8 leading-relaxed">
              Pick a strong password — at least 8 characters. You'll be signed out everywhere after this change.
            </p>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-slate-500 block mb-1.5">New password</label>
                <Input
                  type="password"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  placeholder="Min 8 characters"
                  required
                  autoComplete="new-password"
                  data-testid="reset-pw-input"
                  className="rounded-sm h-10"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-slate-500 block mb-1.5">Confirm password</label>
                <Input
                  type="password"
                  value={pw2}
                  onChange={(e) => setPw2(e.target.value)}
                  placeholder="Type it again"
                  required
                  autoComplete="new-password"
                  data-testid="reset-pw-confirm-input"
                  className="rounded-sm h-10"
                />
              </div>
              <Button
                type="submit"
                disabled={submitting}
                data-testid="reset-submit-btn"
                className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-10 font-semibold tracking-tight w-full"
              >
                {submitting ? "Updating…" : "Update password"}
              </Button>
            </form>
          </>
        )}

        <div className="mt-8 border-t border-slate-200 pt-4">
          <Link
            to="/login"
            className="font-mono text-[11px] uppercase tracking-wider text-slate-600 hover:text-slate-900"
            data-testid="reset-back-to-login"
          >
            ← Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
