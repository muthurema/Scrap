import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ThumbsDown, CheckCircle, Warning, Clock } from "@phosphor-icons/react";

export default function FeedbackQueuePage() {
  const [items, setItems] = useState([]);
  const [reviewed, setReviewed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [annotation, setAnnotation] = useState({});
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/feedback/queue?reviewed=${reviewed}&rating=down`);
      setItems(data.items);
    } catch (e) {
      toast.error("Failed to load review queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [reviewed]);

  const submitAnnotation = async (id) => {
    const text = (annotation[id] || "").trim();
    if (text.length < 2) {
      toast.error("Annotation must be at least 2 characters");
      return;
    }
    setBusy(id);
    try {
      await api.post(`/feedback/${id}/annotate`, { annotation: text });
      toast.success("Annotation saved — future similar queries will use it as authoritative correction");
      setAnnotation((a) => ({ ...a, [id]: "" }));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-8 max-w-5xl" data-testid="feedback-queue-page">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-2">// Human-in-the-loop</div>
          <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-1">Feedback Review</h1>
          <p className="text-slate-600">Answers users flagged as wrong. Your SME annotation becomes authoritative context for future similar questions.</p>
        </div>
        <div className="flex gap-px bg-slate-300 border border-slate-300">
          <button
            onClick={() => setReviewed(false)}
            data-testid="filter-pending"
            className={`px-4 py-2 font-mono text-[10px] uppercase tracking-wider transition-colors ${!reviewed ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}
          >
            Pending
          </button>
          <button
            onClick={() => setReviewed(true)}
            data-testid="filter-reviewed"
            className={`px-4 py-2 font-mono text-[10px] uppercase tracking-wider transition-colors ${reviewed ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}
          >
            Reviewed
          </button>
        </div>
      </div>

      {loading && items.length === 0 ? (
        <div className="text-xs font-mono uppercase tracking-wider text-slate-500">LOADING...</div>
      ) : items.length === 0 ? (
        <div className="border border-slate-300 bg-white p-12 text-center">
          <CheckCircle size={32} weight="bold" className="text-emerald-600 mx-auto mb-3" />
          <div className="font-bold text-lg text-slate-900 mb-1">
            {reviewed ? "No reviewed items yet" : "Nothing pending — great work"}
          </div>
          <div className="text-sm text-slate-600">
            {reviewed
              ? "Annotated answers will appear here once you start reviewing."
              : "Users haven't flagged any answers. Or your SME team is on top of it."}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((it) => (
            <div key={it.id} className="border border-slate-300 bg-white" data-testid={`feedback-${it.id}`}>
              <div className="px-4 py-2.5 bg-rose-50 border-b border-rose-200 flex items-center gap-3">
                <ThumbsDown size={14} weight="bold" className="text-rose-700" />
                <Badge className="font-mono text-[10px] uppercase tracking-wider bg-rose-100 text-rose-800 border border-rose-200 hover:bg-rose-100">Thumbs down</Badge>
                <div className="font-mono text-[10px] text-slate-600">{(it.created_at || "").slice(0, 19).replace("T", " ")}</div>
                <div className="ml-auto text-xs text-slate-700">{it.user_email}</div>
              </div>
              <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">User asked</div>
                  <div className="text-sm bg-slate-50 border border-slate-200 p-3 rounded-sm">{it.user_query || "—"}</div>
                  {it.comment && (
                    <>
                      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mt-3 mb-1">User comment</div>
                      <div className="text-sm bg-amber-50 border border-amber-200 p-3 rounded-sm italic">{it.comment}</div>
                    </>
                  )}
                </div>
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">Assistant answered</div>
                  <div className="text-sm bg-slate-50 border border-slate-200 p-3 rounded-sm max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {(it.assistant_answer || "").slice(0, 1200)}{(it.assistant_answer || "").length > 1200 ? "..." : ""}
                  </div>
                </div>
              </div>
              {it.is_reviewed ? (
                <div className="px-4 py-3 bg-emerald-50 border-t border-emerald-200">
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle size={14} weight="bold" className="text-emerald-700" />
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-emerald-700">SME Correction by {it.annotated_by || "—"}</div>
                  </div>
                  <div className="text-sm text-slate-800 whitespace-pre-wrap">{it.annotation}</div>
                </div>
              ) : (
                <div className="px-4 pb-4">
                  <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">SME correction</div>
                  <Textarea
                    rows={3}
                    placeholder="Explain why the answer was wrong and what the correct answer should be. This becomes authoritative for future similar questions."
                    value={annotation[it.id] || ""}
                    onChange={(e) => setAnnotation({ ...annotation, [it.id]: e.target.value })}
                    className="rounded-sm border-slate-300 mb-2"
                    data-testid={`annotation-${it.id}`}
                  />
                  <Button
                    onClick={() => submitAnnotation(it.id)}
                    disabled={busy === it.id}
                    data-testid={`save-annotation-${it.id}`}
                    className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-9"
                  >
                    {busy === it.id ? "SAVING..." : "SAVE CORRECTION"}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
