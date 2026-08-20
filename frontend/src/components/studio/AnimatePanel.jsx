import React, { useEffect, useMemo, useState } from "react";
import { Film, Loader2, AlertTriangle, Sparkles, Eye, Star, Clock, GitCommitHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

// Turn an approved still into a clip.
//
// The still becomes frame one, so identity is INHERITED rather than re-argued
// per frame — that is the whole reason image-to-video leads here and
// text-to-video is out of scope. It also means the source's verdict is the only
// identity number a clip has: frame scoring is Phase 2, so a clip lands
// `ungated` and says so.
//
// Defaults to Kling on kie. Kling is the owner's chosen look (Wan was rejected
// on how the footage looks, 2026-08-14 — not on cost), and kie carries more
// Kling variants than poyo, whose credits are nearly out.
const DEFAULT_PROVIDER = "kie";

const PROVIDERS = [
  { id: "kie", label: "kie.ai" },
  { id: "poyo", label: "poyo.ai" },
];

export default function AnimatePanel({ catalogue, defaultModel, status, busy, onAnimate, onSuggest,
                                       stills = [], continueFrom = false }) {
  const [provider, setProvider] = useState(DEFAULT_PROVIDER);
  const models = (catalogue || {})[provider] || [];

  // Follow the project default when this provider carries it; otherwise the
  // first model it does carry. Recomputed per provider so switching never
  // leaves a model selected that the new provider cannot render.
  const pick = useMemo(() => {
    const wanted = models.find((m) => m.id === defaultModel);
    return wanted || models[0] || null;
  }, [provider, models.length, defaultModel]);

  const [modelId, setModelId] = useState(null);
  const model = models.find((m) => m.id === modelId) || pick;

  const durations = model?.durations || [5];
  const resolutions = model?.resolutions || [];
  const [duration, setDuration] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [allowUngated, setAllowUngated] = useState(false);

  // AI motion direction. Claude reads the actual frame — how tight the crop is,
  // where her hands are, what is behind her — which is why the suggestions are
  // worth more than a generic motion library: they are about THIS shot.
  const [ideas, setIdeas] = useState(null);   // null | {read, caution, best, suggestions}
  const [reading, setReading] = useState(false);
  const [picked, setPicked] = useState(null);
  // The owner steering. With an idea the three options become three ways to
  // shoot THAT; without one they stay three different readings of the frame.
  const [idea, setIdea] = useState("");
  // The LAST frame, on models that take one. Only kling-3.0 does today, so the
  // slot is driven by the catalogue's `end_frame` flag rather than a model name
  // hardcoded here — a second such model should light this up with no edit.
  const [endId, setEndId] = useState(null);

  // A clip inherits the identity of its first frame. Animating a still the gate
  // did NOT keep buys seconds of footage whose identity was never established at
  // any point — so the server refuses it unless this is explicitly ticked, and
  // the run records that it was a choice rather than an oversight.
  const ungated = !["kept", "reclaimed"].includes(status);
  const dur = durations.includes(duration) ? duration : durations[0];
  const res = resolutions.includes(resolution) ? resolution : (resolutions[0] || "1080p");

  // Suggestions are written to fit a specific clip length — a 5s beat directed
  // into a 10s clip either rushes or loops — so changing the duration retires
  // them rather than leaving advice that no longer applies on screen.
  useEffect(() => { setIdeas(null); setPicked(null); }, [dur]);

  // Switching to a model that cannot take an end frame drops the one chosen —
  // otherwise it would sit selected and unsent, and the clip would quietly not
  // arrive where the picked thumbnail says it will.
  const takesEnd = !!model?.end_frame && !continueFrom;
  // The first model anywhere in the catalogue that accepts an end frame, so the
  // offer below names a real one rather than hardcoding "Kling 3.0".
  const endCapable = useMemo(() => {
    for (const [prov, rows] of Object.entries(catalogue || {})) {
      const hit = (rows || []).find((r) => r.end_frame);
      if (hit) return { provider: prov, ...hit };
    }
    return null;
  }, [catalogue]);
  useEffect(() => { if (!takesEnd) setEndId(null); }, [takesEnd]);
  useEffect(() => { setIdeas(null); setPicked(null); }, [endId]);

  const endShot = stills.find((s) => s.id === endId) || null;
  // The server checks BOTH frames against one allow_ungated flag, so the consent
  // box has to appear for either. Gating it on the start alone left a dead end:
  // a kept start plus an ungated end 409'd with no box on screen to tick.
  const endUngated = !!endShot && !["kept", "reclaimed"].includes(endShot.status);
  const needsConsent = (ungated && !continueFrom) || endUngated;
  const blocked = needsConsent && !allowUngated;

  // `overrideDur` exists so applying a recommended length can re-read at that
  // length in the same click. Reading `dur` from state here would use the value
  // from before setDuration, and the new prompts would be written for the old
  // number — the exact mismatch the beat budget is meant to prevent.
  const ask = async (overrideDur) => {
    // Type-checked rather than `?? dur`: anything that is not a number — a click
    // event from a bare `onClick={ask}`, most of all — falls back instead of
    // being posted as the duration.
    const d = typeof overrideDur === "number" ? overrideDur : dur;
    setReading(true);
    try {
      const r = await onSuggest({ duration: d, idea, end_run_id: endId,
                                  continue_from: continueFrom,
                                  provider, model: model?.id });
      if (r) setIdeas(r);
    } finally { setReading(false); }
  };

  // Claude only rates the length when it has two frames to measure between.
  const rec = ideas?.suggested_duration;
  const recDiffers = !!ideas?.duration_why && !!rec && rec !== dur;

  const take = (s, i) => { setPrompt(s.prompt); setPicked(i); };

  // An idea typed but never suggested-on used to go nowhere: it steers what
  // Claude proposes, and the box below is what reaches the video model, so
  // typing a direction and pressing animate sent the built-in default instead —
  // silently, which is the one thing this panel should never do. It falls
  // through now, and SAYS it is falling through rather than doing it quietly.
  const fallThrough = !prompt.trim() && !!idea.trim();

  const go = () => onAnimate({
    provider, model: model?.id, duration: dur, resolution: res,
    prompt: prompt.trim() || idea.trim(),
    allow_ungated: allowUngated, continue_from: continueFrom,
    end_run_id: takesEnd ? endId : null,
  });

  return (
    <div className="rounded-xl ring-1 ring-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Film className="h-3.5 w-3.5 text-zinc-400" />
        <h4 className="text-[11px] font-semibold text-zinc-300 uppercase tracking-wider">
          {continueFrom ? "Extend this clip" : "Animate this still"}
        </h4>
      </div>

      {continueFrom && (
        <p className="text-[11px] text-zinc-500 leading-snug">
          Continues from this clip's last frame, which is how a sequence runs past a
          model's duration cap. Identity compounds: every link starts from a generated
          frame rather than an approved still.
        </p>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Field label="provider">
          <Select value={provider} onChange={(v) => { setProvider(v); setModelId(null); setDuration(null); setResolution(null); }}
            options={PROVIDERS.map((p) => [p.id, p.label])} />
        </Field>
        <Field label="model">
          <Select value={model?.id || ""} onChange={(v) => { setModelId(v); setDuration(null); setResolution(null); }}
            options={models.map((m) => [m.id, m.label])} />
        </Field>
        <Field label="duration">
          <Select value={String(dur)} onChange={(v) => setDuration(Number(v))}
            options={durations.map((d) => [String(d), `${d}s`])} />
        </Field>
        {resolutions.length > 0 ? (
          <Field label="resolution">
            <Select value={res} onChange={setResolution} options={resolutions.map((r) => [r, r])} />
          </Field>
        ) : (
          // No enum means the model has one fixed output size. Showing a picker
          // that cannot change anything is worse than showing none.
          <Field label="resolution"><div className="px-2 py-1.5 text-[11px] text-zinc-600">fixed by model</div></Field>
        )}
      </div>

      {/* The end-frame capability was invisible: it only appears once a model
          that supports it is chosen, and the default does not. Nobody discovers
          a feature hidden behind a dropdown they had no reason to open. */}
      {!takesEnd && !continueFrom && endCapable && (
        <button onClick={() => { setProvider(endCapable.provider); setModelId(endCapable.id);
                                 setDuration(null); setResolution(null); }}
          className="w-full rounded-lg ring-1 ring-white/10 bg-white/[0.02] hover:bg-white/[0.05] p-2.5 text-left flex items-start gap-2">
          <GitCommitHorizontal className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0 mt-0.5" />
          <span className="text-[10px] text-zinc-400 leading-snug">
            Want it to land on a second shot? <span className="text-zinc-200">{endCapable.label}</span> takes
            a start <span className="text-zinc-200">and</span> an end frame, and interpolates between them.
            <span className="text-zinc-600"> Click to switch.</span>
          </span>
        </button>
      )}

      {takesEnd && (
        <div className="rounded-lg ring-1 ring-white/8 bg-black/20 p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              end frame {endShot ? "· clip lands here" : "· optional"}
            </span>
            {endShot && (
              <button onClick={() => setEndId(null)}
                className="text-[10px] text-zinc-500 hover:text-zinc-300">clear</button>
            )}
          </div>
          <p className="text-[10px] text-zinc-600 leading-snug">
            Pick a second shot and the clip interpolates from this one to that one.
            Two anchors hold the likeness better than one — but the further apart they
            are, the more the model has to invent in between.
            <span className="text-zinc-500"> A dot means the gate kept it.</span>
          </p>
          {stills.length === 0
            ? <p className="text-[10px] text-zinc-600">No other stills to land on yet.</p>
            : (
              // A WRAPPING grid, not a horizontal strip. Scrollbars are hidden
              // app-wide (index.css), so a sideways-overflowing row has no
              // affordance AND a mouse wheel does not scroll it — it just looked
              // stuck. Vertical overflow is what the wheel drives natively.
              <div className="grid grid-cols-8 xl:grid-cols-10 gap-1 max-h-52 overflow-y-auto pr-1">
                {stills.map((s) => {
                  const kept = ["kept", "reclaimed"].includes(s.status);
                  return (
                    <button key={s.id} onClick={() => setEndId(endId === s.id ? null : s.id)}
                      title={`${kept ? "kept" : s.status} · ${s.brief}`}
                      className={cn("relative rounded overflow-hidden ring-1 transition-all",
                        endId === s.id ? "ring-2 ring-violet-400 scale-[0.94]"
                          : "ring-white/10 hover:ring-white/40")}>
                      <img src={s.thumb} alt={s.brief} loading="lazy"
                        className={cn("h-11 w-full object-cover",
                          !kept && endId !== s.id && "opacity-55")} />
                      <span className={cn("absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full ring-1 ring-black/50",
                        kept ? "bg-emerald-400" : "bg-zinc-500")} />
                    </button>
                  );
                })}
              </div>
            )}
        </div>
      )}

      {onSuggest && (
        <div className="rounded-lg ring-1 ring-white/8 bg-black/20 p-3 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              {ideas
                ? (endShot ? `three ways to get there in ${dur}s`
                  : idea.trim() ? `three ways to shoot that in ${dur}s`
                    : `three ways to move this ${dur}s`)
                : endShot ? "not sure how it should get there?" : "not sure what should move?"}
            </span>
            {/* Must be wrapped, not `onClick={ask}` — React passes the click
                event as the first argument, which `ask` would take as its
                duration override and post as the request body. */}
            <button onClick={() => ask()} disabled={reading}
              className={cn("rounded-md px-2.5 py-1 text-[10px] flex items-center gap-1.5 ring-1 transition-colors",
                reading ? "bg-white/5 text-zinc-600 ring-white/10"
                        : "bg-violet-500/15 text-violet-200 ring-violet-400/30 hover:bg-violet-500/25")}>
              {reading
                ? <><Loader2 className="h-3 w-3 animate-spin" /> reading the frame…</>
                : <><Sparkles className="h-3 w-3" /> {ideas ? "re-read" : "suggest"}</>}
            </button>
          </div>

          {/* Steering is optional and goes in before the read, so the frame is
              read against your idea rather than the idea being bolted onto a
              generic answer. Enter fires it — this is a one-line thought. */}
          <input
            value={idea} onChange={(e) => setIdea(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !reading) ask(); }}
            placeholder="your idea, optional — e.g. she laughs and looks away"
            className="w-full rounded-md bg-black/40 ring-1 ring-white/10 px-2.5 py-1.5 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-violet-400/40"
          />

          {ideas && (
            <>
              {/* What Claude actually sees, shown before what it advises — the
                  read is how you judge whether the suggestions are worth taking. */}
              <p className="text-[11px] text-zinc-400 leading-snug flex gap-1.5">
                <Eye className="h-3 w-3 flex-shrink-0 mt-0.5 text-zinc-600" />
                <span>{ideas.read}</span>
              </p>

              {ideas.caution && (
                <p className="text-[10px] text-amber-300/90 leading-snug flex gap-1.5 rounded bg-amber-500/10 ring-1 ring-amber-500/20 p-2">
                  <AlertTriangle className="h-3 w-3 flex-shrink-0 mt-0.5" />
                  <span>{ideas.caution}</span>
                </p>
              )}

              {/* How long the JOURNEY needs — only offered with two frames,
                  because with one there is nothing to arrive at and a number
                  would be taste dressed up as a measurement. */}
              {ideas.duration_why && (
                <div className={cn("rounded p-2 ring-1 flex items-start gap-1.5 text-[10px] leading-snug",
                  recDiffers ? "bg-sky-500/10 ring-sky-400/25 text-sky-200"
                    : "bg-white/[0.03] ring-white/10 text-zinc-400")}>
                  <Clock className="h-3 w-3 flex-shrink-0 mt-0.5" />
                  <span className="flex-1">
                    {recDiffers
                      ? <>This transition wants <span className="font-semibold">{rec}s</span>, not {dur}s. {ideas.duration_why}</>
                      : <>{dur}s fits this transition. {ideas.duration_why}</>}
                  </span>
                  {recDiffers && (
                    <button onClick={() => { setDuration(rec); ask(rec); }}
                      className="flex-shrink-0 rounded bg-sky-500/20 px-1.5 py-0.5 text-sky-100 hover:bg-sky-500/30">
                      use {rec}s
                    </button>
                  )}
                </div>
              )}

              <div className="space-y-1.5">
                {ideas.suggestions.map((s, i) => (
                  <button key={i} onClick={() => take(s, i)}
                    className={cn("w-full text-left rounded-lg p-2.5 ring-1 transition-colors",
                      picked === i ? "bg-violet-500/15 ring-violet-400/40"
                        : i === ideas.best ? "bg-emerald-500/[0.07] ring-emerald-400/25 hover:bg-emerald-500/15"
                          : "bg-white/[0.03] ring-white/8 hover:bg-white/[0.06]")}>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] font-medium text-zinc-200">{s.title}</span>
                      {/* The pick is marked in place rather than sorted to the
                          top, so a re-read is comparable to the last one. */}
                      {i === ideas.best && (
                        <span className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider bg-emerald-500/20 text-emerald-300">
                          <Star className="h-2.5 w-2.5" /> best
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-[10px] text-zinc-400 leading-snug">{s.prompt}</div>
                    <div className="mt-1 text-[10px] text-zinc-600 italic leading-snug">{s.why}</div>
                  </button>
                ))}
              </div>

              {ideas.best_why && (
                <p className="text-[10px] text-emerald-300/80 leading-snug flex gap-1.5">
                  <Star className="h-3 w-3 flex-shrink-0 mt-0.5" />
                  <span>{ideas.best_why}</span>
                </p>
              )}

              <p className="text-[10px] text-zinc-600">
                Pick one to fill the box below — edit it freely, nothing renders until you press animate.
              </p>
            </>
          )}
        </div>
      )}

      <div>
        <label className="text-[9px] uppercase tracking-wider text-zinc-600">what should move</label>
        <textarea
          value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
          placeholder="Gentle natural motion, the camera almost still, her expression unchanged."
          className="mt-1 w-full rounded-lg bg-black/40 ring-1 ring-white/10 px-3 py-2 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-white/25 resize-none"
        />
        {fallThrough && (
          <p className="mt-1 text-[10px] text-violet-300/90 leading-snug flex gap-1.5">
            <Sparkles className="h-3 w-3 flex-shrink-0 mt-0.5" />
            <span>
              Empty, so your idea goes as the motion prompt, word for word:
              <span className="text-zinc-300"> “{idea.trim()}”</span>.
              Press suggest instead to have it read against the frame first.
            </span>
          </p>
        )}
      </div>

      {needsConsent && (
        <label className="flex items-start gap-2 rounded-lg bg-amber-500/10 ring-1 ring-amber-500/20 p-2.5 cursor-pointer">
          <input type="checkbox" checked={allowUngated} onChange={(e) => setAllowUngated(e.target.checked)}
            className="mt-0.5 accent-amber-400" />
          <span className="text-[10px] text-amber-300 leading-snug">
            <AlertTriangle className="inline h-3 w-3 mr-1 -mt-0.5" />
            {ungated && !continueFrom && endUngated
              ? <>Both frames are ungated — the start is <span className="font-semibold">{status}</span> and
                the end is <span className="font-semibold">{endShot.status}</span>.</>
              : endUngated
                ? <>The end frame is <span className="font-semibold">{endShot.status}</span>, so the clip is
                  told to arrive at a shot the gate never established.</>
                : <>This shot is <span className="font-semibold">{status}</span>. A clip inherits the identity
                  of its first frame, so animating it makes {dur}s whose identity was never established.</>}
            {" "}Tick to do it anyway — the run records that you chose to.
          </span>
        </label>
      )}

      <button
        onClick={go} disabled={!!busy || blocked || !model}
        className={cn("w-full rounded-lg py-2 text-[12px] font-medium flex items-center justify-center gap-1.5 ring-1 transition-colors",
          busy || blocked || !model
            ? "bg-white/5 text-zinc-600 ring-white/10 cursor-not-allowed"
            : "bg-indigo-500/15 text-indigo-200 ring-indigo-400/30 hover:bg-indigo-500/25")}
      >
        {busy
          ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> {busy}</>
          : <><Film className="h-3.5 w-3.5" /> {continueFrom ? `extend +${dur}s`
              : endShot ? `animate ${dur}s → end frame` : `animate ${dur}s`}</>}
      </button>

      {busy && (
        <p className="text-[10px] text-zinc-600 text-center">
          Clips render in minutes, not seconds. Leaving this open is not required — the
          run lands in Review when it finishes.
        </p>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg bg-black/40 ring-1 ring-white/10 px-2 py-1.5 text-[11px] text-zinc-200 focus:outline-none focus:ring-white/25">
      {options.map(([v, l]) => <option key={v} value={v} className="bg-[#0d0d0f]">{l}</option>)}
    </select>
  );
}
