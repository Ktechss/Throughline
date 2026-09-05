import React, { useState } from "react";
import { Check, Ban, Shirt, PersonStanding, Copy, AlertTriangle, Maximize2, Loader2, Film } from "lucide-react";
import { cn } from "@/lib/utils";
import { Modal } from "@/components/ui/modal";
import VerdictChip from "./VerdictChip";
import AnimatePanel from "./AnimatePanel";
import { ep, refUrl, apiCharacter } from "@/api/throughline";

// image = a runView/genView object; image.raw is the real run row (full metadata).
export default function ImageDetail({ image, wardrobe = [], onClose, onMark, onToWardrobe, onToPoseRef, onUsePose,
                                      videoCat, animating = {}, onAnimate, onSuggest, stills = [],
                                      source, onOpenSource }) {
  const run = image.raw || {};
  // A clip, not a still. It plays here rather than rendering as an <img>, and
  // the still-only exports below are hidden: topaz takes an image, and
  // /api/wardrobe/from-run and /api/pose-refs/from-run both expect one too.
  const isVideo = image.kind === "video";
  // Upscaled DELIVERY copy. Deliberately not re-scored: measured at x2, face_px
  // went 169 -> 338 while similarity moved -0.0055, because ArcFace embeds a
  // 112x112 crop either way. Bigger pixels, same signal — so this is an export,
  // never an input to the gate.
  const [hires, setHires] = useState(null);   // null | "busy" | "ready" | error string
  const [showAnimate, setShowAnimate] = useState(false);

  const meta = run.meta || {};
  const mark = image.mark || run.mark;
  const face = (meta.bio_references || [])[0];
  const outfitFile = wardrobe.find((w) => w.id === meta.wardrobe)?.file;
  const sanitised = meta.sanitised || [];

  const kv = [
    // run.model is what ACTUALLY rendered; run.endpoint is a legacy label from
    // the fal-era path and reads "kie/nano-banana-pro" no matter which kie model
    // ran. Showing endpoint under the word "model" is how a seedream shot billed
    // at 14.5 credits displayed as nano-banana-pro and looked like the picker was
    // being ignored. Prefer the real field; fall back only for older rows.
    ["model", run.model || ep(run.endpoint)],
    ...(run.provider ? [["provider", run.provider]] : []),
    ...(run.credits ? [["credits", run.credits]] : []),
    ["prompt by", meta.ai_prompt ? "AI / Claude" : "template"],
    ...(meta.body ? [["body type", meta.body]] : []),
    ...(isVideo ? [["duration", `${run.duration ?? "?"}s`]] : [["seed", run.seed ?? "random"]]),
    // A clip's row carries no aspect — it inherits the still's — so the empty
    // cell is dropped rather than shown as a blank labelled field.
    ...(run.aspect ? [["aspect", run.aspect]] : []),
    // Measured, not requested. A silent default-shaped image used to leave no
    // trace: the row said 3:4 / 4K while the file was 1024x768.
    ...(run.width && run.height ? [["pixels", `${run.width} x ${run.height}`]] : []),
    ...(run.seconds ? [["gen time", `${run.seconds}s`]] : []),
    ["created", (run.created || "").replace("T", " ")],
  ];

  const hideOnErr = (e) => { const f = e.currentTarget.closest("figure"); if (f) f.style.display = "none"; };

  return (
    // The verdict IS the title here — sim, yaw and face_px are the first thing
    // to read about a shot, never the filename.
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={
        <VerdictChip status={image.status} pov={image.pov} similarity={image.similarity}
          yaw={image.yaw} facePx={image.facePx} poseMismatch={image.poseMismatch} />
      }
    >
      <div className="space-y-6">
          {(run.verdict?.reason || run.moderation_fallback) && (
            <div className="rounded-lg bg-amber-500/10 ring-1 ring-amber-500/20 p-3 text-[11px] text-amber-300 flex gap-2">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>
                {/* Which confounds explain the score — one chip each, because
                    three stacked is a different problem from any one of them.
                    "drift" is the only one that is about her, so it reads red. */}
                {(run.verdict?.confounds
                  || (run.verdict?.diagnosis ? run.verdict.diagnosis.split("+") : [])
                 ).map((c) => (
                  <span key={c} className={cn("mr-1.5 rounded px-1.5 py-0.5 font-semibold uppercase tracking-wider text-[10px]",
                    c === "drift" ? "bg-red-500/20 text-red-300" : "bg-amber-500/20 text-amber-200")}>
                    {c}
                  </span>
                ))}
                {run.verdict?.reason || "served by the scene model (weaker identity) after a moderation refusal"}
              </span>
            </div>
          )}

          {/* Top: generated image (left) + references (right) */}
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-5">
            <div className="space-y-3">
              <div className="rounded-xl bg-black ring-1 ring-white/5 flex items-center justify-center p-3 min-h-[40vh]">
                {isVideo
                  ? <video src={image.url} poster={image.thumb} controls loop playsInline
                      className="max-h-[62vh] w-auto rounded-lg" />
                  : <img src={image.url} alt={image.brief} className="max-h-[62vh] w-auto rounded-lg object-contain" />}
              </div>
              {showAnimate && onAnimate && (
                <AnimatePanel
                  catalogue={videoCat?.catalogue} defaultModel={videoCat?.default}
                  status={image.status} busy={animating[run.id]} continueFrom={isVideo}
                  onAnimate={(opts) => onAnimate(run.id, opts)}
                  onSuggest={onSuggest && ((opts) => onSuggest(run.id, opts))}
                  stills={stills}
                />
              )}
            </div>
            <div>
              <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">References used</h4>
              <div className="flex flex-wrap gap-3">
                {face && (
                  <figure className="m-0 w-28">
                    <img src={refUrl(face)} onError={hideOnErr} className="h-36 w-28 rounded-lg object-cover ring-1 ring-line" alt="face ref" />
                    <figcaption className="mt-1 truncate text-[10px] text-zinc-500">face · {face}</figcaption>
                  </figure>
                )}
                {outfitFile && (
                  <figure className="m-0 w-28">
                    <img src={`/api/wardrobe/${outfitFile}/file?character=${apiCharacter() || ""}`} onError={hideOnErr} className="h-36 w-28 rounded-lg object-cover ring-1 ring-line" alt="outfit ref" />
                    <figcaption className="mt-1 truncate text-[10px] text-zinc-500">outfit · {meta.wardrobe}</figcaption>
                  </figure>
                )}
                {/* A clip's reference is the frame it started from. `meta.still`
                    cannot be shown directly — for a chained clip it is a
                    "-last.jpg" inside .frames/, which /api/images does not serve
                    — so the SOURCE RUN is resolved by id instead. That also makes
                    the chain walkable: click back through every link to the
                    approved still the sequence started from. */}
                {isVideo && (source
                  ? (
                    <button onClick={() => onOpenSource?.(source)} className="m-0 w-28 text-left group/src">
                      <img src={source.thumb} onError={hideOnErr} className="h-36 w-28 rounded-lg object-cover ring-1 ring-line group-hover/src:ring-white/30" alt="source frame" />
                      <div className="mt-1 truncate text-[10px] text-zinc-500">
                        {meta.continued_from ? "continued from" : "animated from"} · {source.kind === "video" ? "clip" : "still"}
                      </div>
                    </button>
                  )
                  : <p className="text-[11px] text-zinc-600">Source run {meta.from_run || "?"} is no longer in the grid.</p>
                )}
                {!isVideo && !face && !outfitFile && <p className="text-[11px] text-zinc-600">No reference images recorded.</p>}
              </div>
              <p className="mt-3 font-mono text-[10px] text-zinc-600">attached: {(run.refs || []).join(" → ") || "none"}</p>

              {(meta.pose_id || meta.pose_ref) && (
                <div className="mt-4 rounded-lg ring-1 ring-line bg-surface p-3">
                  <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">Pose used</div>
                  <p className="text-[12px] text-zinc-200">{meta.pose_id || "custom pose reference"}</p>
                  {meta.pose_text && <p className="mt-0.5 text-[11px] text-zinc-500 leading-snug line-clamp-3">{meta.pose_text}</p>}
                  {onUsePose && <button onClick={() => onUsePose(run)} className="mt-2 w-full rounded-lg bg-white/10 hover:bg-white/15 py-1.5 text-[11px] text-zinc-200 flex items-center justify-center gap-1.5"><Copy className="h-3 w-3" /> Use this pose</button>}
                </div>
              )}

              {/* Metadata — fills the empty space under the references / pose card */}
              <section className="mt-4">
                <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Metadata</h4>
                <div className="grid grid-cols-2 gap-px rounded-lg overflow-hidden ring-1 ring-line-subtle bg-white/10">
                  {kv.map((x) => (
                    <div key={x[0]} className="bg-[#0d0d0f] p-3">
                      <div className="text-[11px] uppercase tracking-wider text-zinc-600">{x[0]}</div>
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
              <p className="text-[11px] font-mono text-zinc-400 leading-relaxed bg-surface rounded-lg p-4 ring-1 ring-white/5 whitespace-pre-wrap break-words">{run.prompt}</p>
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
      <div className="sticky bottom-0 -mx-4 -mb-3 mt-5 border-t border-white/10 bg-[#0d0d0f]/95 backdrop-blur px-4 py-3 flex flex-wrap items-center gap-2">
          <button onClick={() => onMark(run.id, "approve")} className={cn("rounded-lg px-4 py-2 text-[12px] flex items-center gap-1.5 ring-1", mark === "approve" ? "bg-emerald-500/25 text-emerald-200 ring-emerald-500/40" : "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25 hover:bg-emerald-500/20")}><Check className="h-3.5 w-3.5" /> approve</button>
          <button onClick={() => onMark(run.id, "reject")} className={cn("rounded-lg px-4 py-2 text-[12px] flex items-center gap-1.5 ring-1", mark === "reject" ? "bg-rose-500/25 text-rose-200 ring-rose-500/40" : "bg-rose-500/10 text-rose-300 ring-rose-500/25 hover:bg-rose-500/20")}><Ban className="h-3.5 w-3.5" /> reject</button>
          <div className="flex-1" />
          {onAnimate && (
            <button onClick={() => setShowAnimate((v) => !v)}
              title={isVideo
                ? "Continue from this clip's last frame, past the model's duration cap."
                : "Animate this still. It becomes frame one, so identity is inherited rather than re-argued."}
              className={cn("rounded-lg px-4 py-2 text-[12px] flex items-center gap-1.5 ring-1",
                showAnimate ? "bg-indigo-500/25 text-indigo-200 ring-indigo-400/40"
                            : "ring-line text-zinc-300 hover:bg-white/5")}>
              {animating[run.id]
                ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> {animating[run.id]}</>
                : <><Film className="h-3.5 w-3.5" /> {isVideo ? "extend" : "animate"}</>}
            </button>
          )}
          {!isVideo && run.file && (
            <a href={`/api/images/${run.file}/hires?factor=2`} target="_blank" rel="noreferrer"
              onClick={() => { setHires("busy"); setTimeout(() => setHires("ready"), 1200); }}
              title="Upscaled 2x on topaz for delivery. Not re-scored — the verdict above stays measured on the original."
              className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center gap-1.5">
              {hires === "busy"
                ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> upscaling…</>
                : <><Maximize2 className="h-3.5 w-3.5" /> export 2x</>}
            </a>
          )}
          {!isVideo && (
            <>
              <button onClick={() => onToWardrobe(run.id)} className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center gap-1.5"><Shirt className="h-3.5 w-3.5" /> → wardrobe</button>
              <button onClick={() => onToPoseRef(run.id)} className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center gap-1.5"><PersonStanding className="h-3.5 w-3.5" /> → pose ref</button>
            </>
          )}
      </div>
    </Modal>
  );
}
