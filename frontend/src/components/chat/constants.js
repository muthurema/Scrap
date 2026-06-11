export const SUGGESTIONS = [
  "What is the difference between a geographic and a projected coordinate system?",
  "Explain how a UTM zone is defined.",
  "When should I use a datum transformation vs a reprojection?",
  "Walk me through supervised image classification in remote sensing.",
  "What is the difference between vector and raster data models?",
];

export const DOC_TYPE_LABELS = {
  sop: "Guide", incident_report: "Case Study", risk_assessment: "Analysis",
  regulatory: "Standard", training: "Tutorial", permit: "Reference",
  policy: "Reference", msds: "Reference", general: "Book",
};

export const SOURCE_LABELS = {
  superadmin: { text: "Knowledge Base", color: "bg-emerald-600 text-white" },
  turnstile_dms: { text: "Knowledge Base", color: "bg-emerald-600 text-white" },
  base_corpus: { text: "Knowledge Base", color: "bg-emerald-600 text-white" },
  regional_base: { text: "Knowledge Base", color: "bg-emerald-600 text-white" },
  client_web: { text: "Web Source", color: "bg-sky-600 text-white" },
  platform_web: { text: "Web Source", color: "bg-sky-600 text-white" },
};
