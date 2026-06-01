import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Envelope, PaperPlaneTilt, CheckCircle, WarningCircle, Info } from "@phosphor-icons/react";

/**
 * Superadmin-only SMTP diagnostic.
 *
 * The public `/api/auth/password-reset/request` endpoint intentionally
 * returns 200 even when SMTP fails (anti-enumeration). That makes it
 * impossible to tell from the UI whether emails are actually being
 * delivered. This page hits `/api/admin/smtp/test`, which surfaces the
 * real SMTP exception so the operator can fix the config.
 */
export default function SettingsPage() {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const sendTest = async () => {
    if (!to || !to.includes("@")) {
      toast.error("Enter a valid recipient email");
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post(
        `/admin/smtp/test?to=${encodeURIComponent(to)}`,
      );
      setResult(data);
      if (data.ok) toast.success(`Test email sent to ${to}`);
      else toast.error(`SMTP test failed at: ${data.stage}`);
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || "Request failed";
      setResult({ ok: false, stage: "request", error: detail });
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 lg:p-8 max-w-3xl" data-testid="settings-page">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">
          Operator Tools
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-600 mt-1">
          Diagnostic utilities for the platform operator.
        </p>
      </div>

      {/* SMTP Diagnostic */}
      <section className="border border-slate-200 bg-white" data-testid="smtp-diagnostic-card">
        <div className="border-b border-slate-200 p-5 flex items-center gap-3">
          <div className="w-9 h-9 bg-slate-900 text-white flex items-center justify-center">
            <Envelope size={18} weight="bold" />
          </div>
          <div>
            <div className="font-semibold text-slate-900">SMTP Diagnostic</div>
            <div className="text-xs text-slate-500">
              Send a real test email and surface the actual SMTP error if delivery fails.
            </div>
          </div>
        </div>

        <div className="p-5 space-y-4">
          <div className="bg-amber-50 border border-amber-200 p-3 flex gap-2 text-xs text-amber-900">
            <Info size={16} weight="bold" className="shrink-0 mt-[1px]" />
            <div>
              The public <code className="font-mono">forgot-password</code> endpoint always returns 200
              (to prevent email enumeration). That hides SMTP errors. <strong>Use this tool to see why
              the magic link isn't arriving.</strong>
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-1.5">
              Recipient email
            </label>
            <div className="flex gap-2">
              <Input
                type="email"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="you@example.com"
                data-testid="smtp-test-to-input"
                disabled={busy}
              />
              <Button
                onClick={sendTest}
                disabled={busy || !to}
                data-testid="smtp-test-send-btn"
                className="shrink-0"
              >
                <PaperPlaneTilt size={14} weight="bold" className="mr-1.5" />
                {busy ? "Sending…" : "Send test"}
              </Button>
            </div>
          </div>

          {result && (
            <div
              className={`border p-4 ${
                result.ok
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-rose-200 bg-rose-50"
              }`}
              data-testid="smtp-test-result"
            >
              <div className="flex items-center gap-2 mb-2">
                {result.ok ? (
                  <>
                    <CheckCircle size={18} weight="bold" className="text-emerald-700" />
                    <div className="font-semibold text-emerald-900">Delivered</div>
                  </>
                ) : (
                  <>
                    <WarningCircle size={18} weight="bold" className="text-rose-700" />
                    <div className="font-semibold text-rose-900">
                      Failed at stage: <span className="font-mono">{result.stage}</span>
                    </div>
                  </>
                )}
              </div>

              {!result.ok && result.error && (
                <pre
                  className="font-mono text-xs bg-white border border-rose-200 p-3 whitespace-pre-wrap break-all text-rose-900"
                  data-testid="smtp-test-error"
                >
                  {result.error}
                </pre>
              )}

              {result.config && (
                <div className="mt-3">
                  <div className="text-xs font-mono uppercase tracking-wider text-slate-600 mb-1.5">
                    Current SMTP config
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">
                    {Object.entries(result.config).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <span className="text-slate-500">{k}</span>
                        <span className="text-slate-900 truncate" title={String(v)}>
                          {String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!result.ok && Array.isArray(result.hints) && result.hints.length > 0 && (
                <div className="mt-3 pt-3 border-t border-rose-200">
                  <div className="text-xs font-mono uppercase tracking-wider text-slate-600 mb-1.5">
                    Likely causes
                  </div>
                  <ul className="text-xs text-slate-700 space-y-1 list-disc pl-4">
                    {result.hints.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.ok && (
                <p className="text-xs text-emerald-800">
                  Check the inbox (and spam folder) for <strong>{to}</strong>. If it landed in
                  spam, the forgot-password emails will too — consider switching to a provider
                  with proper SPF/DKIM (SendGrid, Postmark, Mailgun).
                </p>
              )}
            </div>
          )}

          <div className="text-xs text-slate-500 leading-relaxed pt-2 border-t border-slate-100">
            Required env vars on Railway:{" "}
            <code className="font-mono">SMTP_HOST</code>,{" "}
            <code className="font-mono">SMTP_PORT</code> (587 for STARTTLS, 465 for SSL),{" "}
            <code className="font-mono">SMTP_USERNAME</code>,{" "}
            <code className="font-mono">SMTP_PASSWORD</code>,{" "}
            <code className="font-mono">SMTP_FROM</code> (optional, defaults to username),{" "}
            <code className="font-mono">SMTP_USE_TLS</code> (default: true).{" "}
            Also set <code className="font-mono">PASSWORD_RESET_FRONTEND_URL</code> so the magic
            link points to your custom domain instead of the Railway URL.
          </div>
        </div>
      </section>
    </div>
  );
}
