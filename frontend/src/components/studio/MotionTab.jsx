import React, { useState } from "react";
import { Film, ArrowRight, ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import VerdictChip from "./VerdictChip";
import AnimatePanel from "./AnimatePanel";

// Video gets its own page rather than living inside the shot-detail modal.
//
// Animating is not a property of one photograph the way "export 2x" is — it
// takes a START frame, optionally an END frame, a model, a length and a written
// direction, and it produces a different KIND of asset that the gate cannot
// score. Cramming all of that into a modal opened on one image made the second
// frame feel like an afterthought and left no room to see the clips afterwards.
const KEPT = ["kept", "reclaimed"];
const isKept = (s) => KEPT.includes(s.status);

export default function MotionTab({ shots = [], videoCat, animating = {}, onAnimate, onSuggest }) {
  // EVERY still is offered, not just the gate-kept ones. The gate's verdict is
  // information, not a lock: it is shown on each tile and the panel still makes
  // you tick a box before animating an ungated shot, but which frames are worth
  // moving is the owner's call — the same axis the `mark` field exists for.
  const stills = shots.filter((s) => s.kind !== "video");
  const clips = shots.filter((s) => s.kind === "video");
  const keptCount = stills.filter(isKept).length;

  const [filter, setFilter] = useState("all");   // all | kept | rest
  const listed = filter === "kept" ? stills.filter(isKept)
    : filter === "rest" ? stills.filter((s) => !isKept(s))
      : stills;

  const [startId, setStartId] = useState(null);
  const start = stills.find((s) => s.id === startId) || null;

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-[15px] font-semibold text-zinc-100 flex items-center gap-2">
            <Film className="h-4 w-4 text-zinc-400" /> Motion
          </h2>
          <p className="mt-1 text-[11px] text-zinc-500 max-w-2xl leading-snug">
            A clip inherits the identity of its first frame, so it starts from a shot the
            gate already kept — only those are offered below. Clips are never gated
            themselves: frame scoring is Phase 2, so what comes back is honestly unmeasured
            rather than falsely clean.
          </p>
        </div>
        <div className="flex items-center gap-6">
          <Metric label="Stills" value={stills.length} />
          <Metric label="Gate-kept" value={keptCount} accent="emerald" />
          <Metric label="Clips" value={clips.length} accent="indigo" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.05fr] gap-6 items-start">
        {/* ---------------------------------------------------- start frame */}
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
              Start frame {start ? "" : "· pick one to begin"}
            </h3>
            <div className="flex items-center gap-1">
              {[["all", "all", stills.length],
                ["kept", "kept", keptCount],
                ["rest", "not kept", stills.length - keptCount]].map(([id, label, n]) => (
                <button key={id} onClick={() => setFilter(id)}
                  className={cn("rounded-md px-2 py-0.5 text-[10px] transition-colors",
                    filter === id ? "bg-white/15 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-white/5")}>
                  {label} <span className="tabular-nums opacity-60">{n}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl bg-black ring-1 ring-white/5 flex items-center justify-center p-3 min-h-[240px]">
            {start
              ? <img src={start.url} alt={start.brief} className="max-h-[42vh] w-auto rounded-lg object-contain" />
              : (
                <div className="text-center text-zinc-600">
                  <ImageIcon className="h-7 w-7 mx-auto mb-2" strokeWidth={1.5} />
                  <p className="text-[11px]">No start frame chosen</p>
                </div>
              )}
          </div>

          {start && (
            <div className="flex items-center justify-between gap-3">
              <VerdictChip status={start.status} pov={start.pov} similarity={start.similarity}
                yaw={start.yaw} facePx={start.facePx} />
              <span className="text-[11px] text-zinc-500 truncate">{start.brief}</span>
            </div>
          )}

          {/* A wrapping grid that scrolls VERTICALLY. Scrollbars are hidden
              app-wide, so a sideways row is unreachable with a wheel.
              lazy loading matters here — this is hundreds of thumbnails now,
              not the dozen the kept-only list used to be. */}
          <div className="grid grid-cols-8 sm:grid-cols-10 xl:grid-cols-12 gap-1 max-h-72 overflow-y-auto pr-1">
            {listed.map((s) => (
              <button key={s.id} onClick={() => setStartId(s.id === startId ? null : s.id)}
                title={`${isKept(s) ? "kept" : s.status} · ${s.brief}`}
                className={cn("relative rounded overflow-hidden ring-1 transition-all",
                  s.id === startId ? "ring-2 ring-emerald-400 scale-[0.94]"
                    : "ring-line hover:ring-white/40")}>
                <img src={s.thumb} alt={s.brief} loading="lazy"
                  className={cn("h-11 w-full object-cover",
                    !isKept(s) && s.id !== startId && "opacity-55")} />
                {/* The verdict rides on the tile rather than gating the list —
                    you can pick anything, you just always know what you picked. */}
                <span className={cn("absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full ring-1 ring-black/50",
                  isKept(s) ? "bg-emerald-400" : "bg-zinc-500")} />
              </button>
            ))}
          </div>
          {listed.length === 0 && (
            <p className="text-[11px] text-zinc-600">Nothing in this filter.</p>
          )}
          {start && !isKept(start) && (
            <p className="text-[10px] text-amber-300/90 leading-snug">
              This shot is <span className="font-semibold">{start.status}</span> — the clip
              will inherit an identity the gate never established. The panel will ask you to
              confirm before it renders.
            </p>
          )}
        </section>

        {/* --------------------------------------------------------- panel */}
        <section>
          {start
            ? (
              <AnimatePanel
                catalogue={videoCat?.catalogue} defaultModel={videoCat?.default}
                status={start.status} busy={animating[start.id]}
                onAnimate={(opts) => onAnimate(start.id, opts)}
                onSuggest={(opts) => onSuggest(start.id, opts)}
                stills={stills.filter((s) => s.id !== start.id)}
              />
            ) : (
              <div className="rounded-xl ring-1 ring-line bg-surface p-8 text-center">
                <ArrowRight className="h-5 w-5 mx-auto mb-2 text-zinc-700" />
                <p className="text-[12px] text-zinc-500">
                  Choose a start frame and the model, length, direction and end-frame
                  controls appear here.
                </p>
              </div>
            )}
        </section>
      </div>

      {/* ---------------------------------------------------------- clips */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-zinc-200">Clips</h3>
          <span className="text-[11px] text-zinc-600 tabular-nums">{clips.length}</span>
        </div>
        {clips.length === 0
          ? <p className="text-[11px] text-zinc-600">Nothing animated yet.</p>
          : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {clips.map((c) => (
                <div key={c.id} className="rounded-xl ring-1 ring-line-subtle bg-surface overflow-hidden">
                  <video src={c.url} poster={c.thumb} controls loop playsInline
                    className="w-full aspect-[4/5] object-cover bg-black" />
                  <div className="px-2.5 py-2 space-y-1">
                    <div className="text-[11px] text-zinc-300 line-clamp-1">{c.brief}</div>
                    <div className="flex items-center gap-2 text-[10px] text-zinc-600">
                      <span className="rounded bg-white/5 px-1.5 py-0.5">{c.duration ?? "?"}s</span>
                      {/* Two anchors is worth surfacing — it is the difference
                          between a clip that wanders and one that has to land. */}
                      {(c.raw?.refs || []).length > 1 && (
                        <span className="rounded bg-violet-500/15 text-violet-300 px-1.5 py-0.5">
                          start → end
                        </span>
                      )}
                      <span className="truncate">{c.raw?.model}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
      </section>
    </div>
  );
}

function Metric({ label, value, accent }) {
  return (
    <div>
      <div className={cn("text-xl font-semibold tabular-nums",
        accent === "indigo" ? "text-indigo-300" : "text-zinc-100")}>{value}</div>
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5">{label}</div>
    </div>
  );
}
