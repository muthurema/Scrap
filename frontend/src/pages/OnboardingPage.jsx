import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { ShieldCheck, ArrowRight } from "@phosphor-icons/react";

const JURISDICTIONS = [
  ["US", "United States — OSHA / EPA / NFPA"],
  ["UK", "United Kingdom — HSE"],
  ["EU", "European Union — EU-OSHA / REACH / Directives"],
  ["AU", "Australia — WHS Act / Safe Work Australia"],
  ["IN", "India — Factories Act / DGMS"],
  ["CA", "Canada — CCOHS"],
  ["GLOBAL", "Global / Multi-region"],
];

const INDUSTRIES = [
  ["construction", "Construction"],
  ["manufacturing", "Manufacturing"],
  ["oil_gas", "Oil & Gas"],
  ["mining", "Mining"],
  ["chemical", "Chemical"],
  ["pharma", "Pharmaceutical"],
  ["logistics", "Logistics / Warehousing"],
  ["utilities", "Utilities"],
  ["healthcare", "Healthcare"],
  ["office", "Office / Corporate"],
  ["agriculture", "Agriculture"],
  ["marine", "Marine"],
  ["other", "Other"],
];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [site, setSite] = useState("");
  const [roleLabel, setRoleLabel] = useState("");
  const [jurisdiction, setJurisdiction] = useState("US");
  const [industry, setIndustry] = useState("manufacturing");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.patch("/users/me", {
        site, role_label: roleLabel, jurisdiction, industry_sector: industry,
      });
      // Persist local user object change (e.g. needs_onboarding=false)
      try {
        const stored = JSON.parse(sessionStorage.getItem("ehs_user") || "null");
        if (stored) {
          stored.needs_onboarding = false;
          stored.jurisdiction = jurisdiction;
          sessionStorage.setItem("ehs_user", JSON.stringify(stored));
        }
      } catch (err) {
        console.warn("[onboarding] could not update local user:", err?.message);
      }
      toast.success("Profile saved");
      navigate(user?.role === "superadmin" ? "/admin/stats" : "/chat");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6" data-testid="onboarding-page">
      <div className="w-full max-w-xl bg-white border border-slate-200 p-8 rounded-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-9 h-9 bg-slate-900 flex items-center justify-center">
            <ShieldCheck size={20} weight="bold" className="text-white" />
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">One-time setup</div>
            <div className="font-bold text-xl tracking-tight">Tell us about your work</div>
          </div>
        </div>
        <p className="text-slate-600 text-sm mb-6">
          This helps the assistant tailor answers (jurisdiction-aware regulations, industry-relevant procedures, and site-specific context).
        </p>
        <form onSubmit={save} className="space-y-4">
          <div className="space-y-1.5">
            <Label className="font-mono text-xs uppercase tracking-wider">Site / Location (optional)</Label>
            <Input value={site} onChange={(e) => setSite(e.target.value)} placeholder="e.g. Texas Plant 3, North Sea Rig 7" data-testid="onboard-site" />
          </div>
          <div className="space-y-1.5">
            <Label className="font-mono text-xs uppercase tracking-wider">Your role (optional)</Label>
            <Input value={roleLabel} onChange={(e) => setRoleLabel(e.target.value)} placeholder="e.g. Safety Officer, Plant Manager, Driller" data-testid="onboard-role" />
          </div>
          <div className="space-y-1.5">
            <Label className="font-mono text-xs uppercase tracking-wider">Regulatory jurisdiction</Label>
            <Select value={jurisdiction} onValueChange={setJurisdiction}>
              <SelectTrigger data-testid="onboard-jurisdiction"><SelectValue /></SelectTrigger>
              <SelectContent>
                {JURISDICTIONS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="text-[11px] text-slate-500">Answers will preference sources from this jurisdiction; cross-jurisdiction citations are flagged.</div>
          </div>
          <div className="space-y-1.5">
            <Label className="font-mono text-xs uppercase tracking-wider">Industry sector</Label>
            <Select value={industry} onValueChange={setIndustry}>
              <SelectTrigger data-testid="onboard-industry"><SelectValue /></SelectTrigger>
              <SelectContent>
                {INDUSTRIES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={busy} data-testid="onboard-submit" className="w-full rounded-sm bg-blue-600 hover:bg-blue-700 text-white h-11 font-semibold tracking-tight group">
            {busy ? "SAVING..." : <span className="flex items-center justify-center gap-2">SAVE & CONTINUE <ArrowRight size={18} weight="bold" className="group-hover:translate-x-0.5 transition-transform" /></span>}
          </Button>
          <button
            type="button"
            onClick={() => navigate(user?.role === "superadmin" ? "/admin/stats" : "/chat")}
            data-testid="onboard-skip"
            className="w-full text-xs text-slate-500 hover:text-slate-800 font-mono uppercase tracking-wider"
          >
            Skip for now
          </button>
        </form>
      </div>
    </div>
  );
}
