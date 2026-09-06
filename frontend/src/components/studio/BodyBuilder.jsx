import React, { useState } from "react";
import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/ui/chip";
import { BodySilhouette } from "@/components/ui/BodySilhouette";

// HER FIGURE, AS SIX DIALS AND A DIAGRAM.
//
// The wizard used to be strictly LESS expressive than the data model under it:
// a character already carries eight body.* parts with real text, and creation
// asked for one word out of five. Everything else was decided by defaults the
// person creating her never saw.
//
// Three things this has to get right, in order:
//
// 1. FRIENDLY BY DEFAULT. "More granular" and "more user friendly" pull in
//    opposite directions, and six raw sliders is LESS friendly than one chip
//    row. So presets are the whole interface until you ask for more: pick
//    "curvy" and move on. Fine tune is one click away and pre-filled from the
//    preset, so it is always an edit on top of something sensible rather than
//    a blank form.
//
// 2. THE PRESET AND THE SLIDERS ARE ONE CONTROL. Picking a preset MOVES the
//    sliders (BUILD_AXIS_DEFAULTS on the server). Before, the picker wrote
//    body.frame and left bust/waist/hips at defaults that contradicted it —
//    a bio reading "full-figured hourglass" directly above Kiara's spec-sheet
//    numbers, on every shot.
//
// 3. NO IMPLIED PROMISES. Each rung shows the SENTENCE it writes into her bio,
//    because that text is what build_clause() sends to the model. And the
//    footnote says plainly that this is a request, not a guarantee: this
//    project measured that text regresses toward slim, which is precisely why
//    these controls exist. A photoreal preview would have implied otherwise;
//    a diagram promises proportions, which is what is actually being set.

export default function BodyBuilder({ axesSpec, presets, build, onBuild,
                                      axes, onAxes, builds = [] }) {
  const [tuning, setTuning] = useState(false);
  const keys = Object.keys(axesSpec || {});
  if (!keys.length) return null;

  // What the diagram draws and what the sliders read: the preset's position,
  // with any explicit edit layered on top. One resolved object, so the two can
  // never disagree.
  const base = (build && presets?.[build]) || {};
  const val = (k) => (axes?.[k] ?? base[k] ?? axesSpec[k].default);
  const resolved = Object.fromEntries(keys.map((k) => [k, val(k)]));
  const edited = keys.filter((k) => axes?.[k] != null && axes[k] !== (base[k] ?? axesSpec[k].default));

  const setAxis = (k) => (e) => onAxes({ ...(axes || {}), [k]: Number(e.target.value) });

  return (
    <div className="rounded-xl bg-surface ring-1 ring-line-subtle overflow-hidden">
      <div className="flex gap-4 p-4">
        {/* The diagram. Deliberately schematic — see BodySilhouette. */}
        <div className="shrink-0 w-[104px] text-ink-subtle">
          <BodySilhouette axes={resolved} showGuides={tuning}
            className="h-[210px] w-full" />
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <div className="text-[11px] font-medium text-ink-subtle mb-1.5">Build</div>
            <div className="flex flex-wrap gap-2">
              {builds.map((b) => (
                <Chip key={b} selected={build === b} onClick={() => onBuild(b)}>
                  {b}
                </Chip>
              ))}
            </div>
          </div>

          <button type="button" onClick={() => setTuning((t) => !t)}
            aria-expanded={tuning}
            className="flex items-center gap-1.5 text-[12px] text-ink-subtle hover:text-ink">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Fine tune
            {edited.length > 0 && (
              <span className="rounded-full bg-white/10 px-1.5 text-[10px] text-ink">
                {edited.length}
              </span>
            )}
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", tuning && "rotate-180")} />
          </button>

          {!tuning && (
            <p className="text-[11px] leading-relaxed text-ink-faint">
              {build
                ? `Sets her bust, waist, hips, thighs and proportions together. Fine tune to change any one of them.`
                : `Pick a build, or fine tune each proportion yourself.`}
            </p>
          )}
        </div>
      </div>

      {tuning && (
        <div className="border-t border-line-subtle p-4 space-y-3.5">
          {keys.map((k) => {
            const spec = axesSpec[k];
            const i = val(k);
            const step = spec.steps[i];
            const isEdited = edited.includes(k);
            return (
              <div key={k}>
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <label className="text-[11px] font-medium text-ink-subtle">
                    {spec.label}
                  </label>
                  <span className={cn("text-[11px]", isEdited ? "text-ink" : "text-ink-subtle")}>
                    {step?.label}
                    {isEdited && (
                      <button type="button"
                        onClick={() => {
                          const next = { ...(axes || {}) };
                          delete next[k];
                          onAxes(next);
                        }}
                        className="ml-1.5 rounded px-1 text-[10px] text-ink-faint hover:text-ink">
                        reset
                      </button>
                    )}
                  </span>
                </div>
                <input type="range" min={0} max={spec.steps.length - 1} step={1}
                  value={i} onChange={setAxis(k)}
                  aria-label={spec.label}
                  aria-valuetext={step?.label}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line accent-rose-400
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40" />
                {/* The sentence that will actually be written into her bio.
                    build_clause() joins this text and sends it to the model, so
                    showing it is the difference between a control and a
                    decoration. */}
                <p className="mt-1 text-[11px] italic leading-snug text-ink-faint">
                  “{step?.text}”
                </p>
              </div>
            );
          })}

          <p className="pt-1 text-[11px] leading-relaxed text-ink-faint border-t border-line-subtle">
            These become her written figure and ride on every shot. They are a
            request, not a guarantee — generators drift toward slim, which is
            why the wording is explicit. Her body <em>reference image</em> is the
            stronger lever; this steers on top of it.
          </p>
        </div>
      )}
    </div>
  );
}
