export const SUGGESTIONS = [
  "What are the OSHA requirements for confined space entry?",
  "Walk me through a hot work permit procedure.",
  "Explain the lockout/tagout 6-step procedure.",
  "How do I conduct a Job Safety Analysis?",
  "What goes into a proper incident root cause analysis?",
];

export const DOC_TYPE_LABELS = {
  sop: "SOP", incident_report: "Incident", risk_assessment: "Risk / HAZOP",
  regulatory: "Regulatory", training: "Training", permit: "Permit",
  policy: "Policy", msds: "MSDS / SDS", general: "General",
};

export const SOURCE_LABELS = {
  superadmin: { text: "Company", color: "bg-blue-600 text-white" },
  turnstile_dms: { text: "Turnstile DMS", color: "bg-indigo-600 text-white" },
  base_corpus: { text: "Base Corpus", color: "bg-slate-700 text-white" },
  client_web: { text: "Client Web", color: "bg-emerald-600 text-white" },
  platform_web: { text: "Platform Web", color: "bg-amber-500 text-slate-900" },
};
