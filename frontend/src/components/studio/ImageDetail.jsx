import React from "react";
import { X, Check, Ban, Shirt, PersonStanding, Copy, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import VerdictChip from "./VerdictChip";
import { ep } from "@/api/throughline";

// image = a runView/genView object; image.raw is the real run row (full metadata).
export default function ImageDetail({ image, wardrobe = [], onClose, onMark, onToWardrobe, onToPoseRef, onUsePose }) {
  const run = image.raw || {};
  const meta = run.meta || {};
  const mark = image.mark || run.mark;
  const face = (meta.bio_references || [])[0];
  const outfitFile = wardrobe.find((w) => w.id === meta.wardrobe)?.file;
  const sanitised = meta.sanitised || [];

  const kv = [
    ["model", ep(run.endpoint)],
    ["prompt by", meta.ai_prompt ? "AI / Claude" : "template"],
    ...(meta.body ? [["body type", meta.body]] : []),
    ["seed", run.seed ?? "random"],
    ["aspect", run.aspect],
    ...(run.seconds ? [["gen time", `${run.seconds}s`]] : []),
    ["created", (run.created || "").replace("T", " ")],
  ];

  const hideOnErr = (e) => { const f = e.currentTarget.closest("figure"); if (f) f.style.display = "none"; };

  return (
    <div onMouseDown={onClose} className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 backdrop-blur-sm p-4 md:p-8">
      <div onMouseDown={(e) => e.stopPropagation()}
        className="relative my-auto w-full max-w-6xl rounded-2xl border border-white/10 bg-[#0d0d0f] flex max-h-[92vh] flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <VerdictChip status={image.status} pov={image.pov} similarity={image.similarity} yaw={image.yaw} facePx={image.facePx} poseMismatch={image.poseMismatch} />
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        {/* Scrollable body (scrollbar hidden globally) */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {(run.verdict?.reason || run.moderation_fallback) && (
            <div className="rounded-lg bg-amber-500/10 ring-1 ring-amber-500/20 p-3 text-[11px] text-amber-300 flex gap-2">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>
                {/* Which confound explains the score. "drift" is the only one that
                    is about her; the rest are framing, and read as red not amber. */}
                {run.verdict?.diagnosis && (
                  <span className={cn("mr-2 rounded px-1.5 py-0.5 font-semibold uppercase tracking-wider text-[10px]",
                    run.verdict.diagnosis === "drift"
                      ? "bg-red-500/20 text-red-300"
                      : "bg-amber-500/20 text-amber-200")}>
                    {run.verdict.diagnosis}
                  </span>
                )}
                {run.verdict?.reason || "served by the scene model (weaker identity) after a moderation refusal"}
              </span>
            </div>
          )}

          {/* Top: generated image (left) + references (right) */}
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-5">
            <div className="rounded-xl bg-black ring-1 ring-white/5 flex items-center justify-center p-3 min-h-[40vh]">
              <img src={image.url} alt={image.brief} className="max-h-[62vh] w-auto rounded-lg object-contain" />
            </div>
            <div>
              <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">References used</h4>
              <div className="flex flex-wrap gap-3">
                {face && (
                  <figure className="m-0 w-28">
                    <img src={`/api/refs/${face}/file`} onError={hideOnErr} className="h-36 w-28 rounded-lg object-cover ring-1 ring-white/10" alt="face ref" />
                    <figcaption className="mt-1 truncate text-[10px] text-zinc-500">face · {face}</figcaption>
                  </figure>
                )}
                {outfitFile && (
                  <figure className="m-0 w-28">
                    <img src={`/api/wardrobe/${outfitFile}/file`} onError={hideOnErr} className="h-36 w-28 rounded-lg object-cover ring-1 ring-white/10" alt="outfit ref" />
                    <figcaption className="mt-1 truncate text-[10px] text-zinc-500">outfit · {meta.wardrobe}</figcaption>
                  </figure>
                )}
                {!face && !outfitFile && <p className="text-[11px] text-zinc-600">No reference images recorded.</p>}
              </div>
              <p className="mt-3 font-mono text-[10px] text-zinc-600">attached: {(run.refs || []).join(" → ") || "none"}</p>

              {(meta.pose_id || meta.pose_ref) && (
                <div className="mt-4 rounded-lg ring-1 ring-white/10 bg-white/[0.02] p-3">
                  <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">Pose used</div>
                  <p className="text-[12px] text-zinc-200">{meta.pose_id || "custom pose reference"}</p>
                  {meta.pose_text && <p className="mt-0.5 text-[11px] text-zinc-500 leading-snug line-clamp-3">{meta.pose_text}</p>}
                  {onUsePose && <button onClick={() => onUsePose(run)} className="mt-2 w-full rounded-lg bg-white/10 hover:bg-white/15 py-1.5 text-[11px] text-zinc-200 flex items-center justify-center gap-1.5"><Copy className="h-3 w-3" /> Use this pose</button>}
                </div>
              )}

              {/* Metadata — fills the empty space under the references / pose card */}
              <section className="mt-4">
                <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Metadata</h4>
                <div className="grid grid-cols-2 gap-px rounded-lg overflow-hidden ring-1 ring-white/8 bg-white/8">
                  {kv.map((x) => (
                    <div key={x[0]} className="bg-[#0d0d0f] p-3">
                      <div className="text-[9px] uppercase tracking-wider text-zinc-600">{x[0]}</div>
                      <div className="mt-1 text-[12px] font-mono text-zinc-200 truncate">{String(x[1])}</div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>

          {meta.brief && (
            <section>
              <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Shot brief</h4>
              <p className="text-[12px] text-zinc-300 leading-relaxed">{meta.brief}</p>
            </section>
          )}

          {/* Full prompt — full width, roomy */}
          {run.prompt && (
            <section>
              <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Full prompt sent</h4>
              <p className="text-[11px] font-mono text-zinc-400 leading-relaxed bg-white/[0.02] rounded-lg p-4 ring-1 ring-white/5 whitespace-pre-wrap break-words">{run.prompt}</p>
            </section>
          )}

          {sanitised.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Sanitised {sanitised.length} phrase{sanitised.length > 1 ? "s" : ""}</h4>
              <div className="text-[11px] space-y-1">
                {sanitised.map((c, i) => (
                  <div key={i} className="font-mono"><span className="line-through text-rose-300">{c.was}</span> <span className="text-zinc-600">→</span> <span className="text-emerald-300">{c.now}</span></div>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Actions pinned at the bottom */}
        <div className="border-t border-white/5 px-5 py-3 flex flex-wrap items-center gap-2">
          <button onClick={() => onMark(run.id, "approve")} className={cn("rounded-lg px-4 py-2 text-[12px] flex items-center gap-1.5 ring-1", mark === "approve" ? "bg-emerald-500/25 text-emerald-200 ring-emerald-500/40" : "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25 hover:bg-emerald-500/20")}><Check className="h-3.5 w-3.5" /> approve</button>
          <button onClick={() => onMark(run.id, "reject")} className={cn("rounded-lg px-4 py-2 text-[12px] flex items-center gap-1.5 ring-1", mark === "reject" ? "bg-rose-500/25 text-rose-200 ring-rose-500/40" : "bg-rose-500/10 text-rose-300 ring-rose-500/25 hover:bg-rose-500/20")}><Ban className="h-3.5 w-3.5" /> reject</button>
          <div className="flex-1" />
          <button onClick={() => onToWardrobe(run.id)} className="rounded-lg ring-1 ring-white/10 px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center gap-1.5"><Shirt className="h-3.5 w-3.5" /> → wardrobe</button>
          <button onClick={() => onToPoseRef(run.id)} className="rounded-lg ring-1 ring-white/10 px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center gap-1.5"><PersonStanding className="h-3.5 w-3.5" /> → pose ref</button>
        </div>
      </div>
    </div>
  );
}
