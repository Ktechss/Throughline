import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/api/throughline";
import { cn } from "@/lib/utils";
import { BodySilhouette } from "@/components/ui/BodySilhouette";

// THE LADDER, AFTER CREATION.
//
// The six body axes were write-once: the wizard had sliders, and from then on
// the only route to her figure was a row of raw textareas. For a project whose
// whole premise is the same woman over a year — "hundreds of images of the
// same woman without identity drift" — a body you can specify once and never
// adjust is the wrong shape. This is the same ladder, mounted on the Bio tab.
//
// THE HONEST PART, and the reason this is not just the wizard's component
// moved: a stored sentence need not be on the ladder at all. Kiara's waist
// reads "a 30-inch waist, clearly defined" — hand-written, measured, and
// matching no rung. Snapping a slider to the nearest rung would silently
// misrepresent her, and the first drag would overwrite a line someone chose
// deliberately. So an unmatched part reads CUSTOM, sits off the ladder, and
// says what it actually contains. Moving its slider is then an explicit,
// visible replacement rather than an accident.
//
// The raw text inputs below this stay. They are the escape hatch the ladder
// cannot replace: five rungs cannot express "30-inch", and this project's own
// body text is full of measurements the ladder deliberately does not carry.

/** Which rung this exact sentence is, or null if it is off the ladder. */
function rungOf(spec, text) {
  if (!text) return null;
  const i = spec.steps.findIndex((s) => s.text === text.trim());
  return i === -1 ? null : i;
}

export default function BodyDials({ parts, onSavePart }) {
  // Fetched here rather than threaded down from BioTab: the ladder is served
  // by /api/characters/options precisely so it has ONE home, and passing it
  // through three components just to reach this one would be a second place
  // for it to go stale. Fails closed — no spec, no dials, raw text still works.
  const [axesSpec, setAxesSpec] = useState(null);
  useEffect(() => {
    api.get("/api/characters/options")
      .then((d) => setAxesSpec(d.body_axes || null))
      .catch(() => {});
  }, []);

  const keys = Object.keys(axesSpec || {});
  const byId = useMemo(
    () => Object.fromEntries((parts || []).map((p) => [p.id, p])), [parts]);

  const rows = keys.map((k) => {
    const spec = axesSpec[k];
    const part = byId[spec.part];
    return { key: k, spec, part, rung: rungOf(spec, part?.text) };
  }).filter((r) => r.part);

  if (!rows.length) return null;

  // The diagram needs a rung for every axis. A custom part has none, so it
  // falls back to the axis default FOR DRAWING ONLY — and the row says so, so
  // the figure is never read as a claim about text it cannot represent.
  const drawn = Object.fromEntries(
    rows.map((r) => [r.key, r.rung ?? r.spec.default]));
  const custom = rows.filter((r) => r.rung === null);

  return (
    <div className="rounded-xl ring-1 ring-line-subtle bg-surface overflow-hidden mb-5">
      <div className="flex gap-4 p-4">
        <div className="shrink-0 w-[92px] text-ink-subtle">
          <BodySilhouette axes={drawn} className="h-[190px] w-full" showGuides />
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <h4 className="text-[12px] font-semibold text-zinc-300">Her figure</h4>
            <p className="text-[11px] text-zinc-500 mt-0.5 leading-snug">
              Each dial rewrites one line below. That text is what reaches the
              model on every shot.
            </p>
          </div>

          {custom.length > 0 && (
            <p className="text-[11px] leading-snug text-amber-300/80">
              {custom.map((r) => r.spec.label).join(", ")}{" "}
              {custom.length === 1 ? "is" : "are"} written by hand and not on the
              ladder — the diagram shows a default for {custom.length === 1 ? "it" : "them"}.
              Moving {custom.length === 1 ? "that dial" : "those dials"} replaces the text.
            </p>
          )}
        </div>
      </div>

      <div className="border-t border-line-subtle p-4 grid gap-3.5 grid-cols-[repeat(auto-fill,minmax(280px,1fr))]">
        {rows.map(({ key, spec, part, rung }) => {
          const shown = rung ?? spec.default;
          return (
            <div key={key} className={cn(!part.enabled && "opacity-50")}>
              <div className="flex items-baseline justify-between gap-3 mb-1">
                <label className="text-[11px] font-medium text-ink-subtle">
                  {spec.label}
                </label>
                <span className={cn("text-[11px]",
                  rung === null ? "text-amber-300/80" : "text-ink")}>
                  {rung === null ? "custom" : spec.steps[rung].label}
                </span>
              </div>
              <input type="range" min={0} max={spec.steps.length - 1} step={1}
                value={shown}
                disabled={!part.enabled}
                onChange={(e) =>
                  onSavePart?.(spec.part, { text: spec.steps[Number(e.target.value)].text })}
                aria-label={spec.label}
                aria-valuetext={rung === null ? "custom" : spec.steps[rung].label}
                className={cn(
                  "h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40",
                  rung === null ? "accent-amber-400/60" : "accent-rose-400",
                  !part.enabled && "cursor-default")} />
              <p className="mt-1 text-[11px] italic leading-snug text-ink-faint line-clamp-2">
                “{part.text}”
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
