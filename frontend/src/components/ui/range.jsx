import React from "react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

// A RANGE THAT CAN HONESTLY SAY "NOTHING CHOSEN".
//
// The age control was a slider parked at 26 with the value actually `null`. That
// is a rendered claim the user never made: the UI told them "she is 26" while
// telling the backend "no age given", and one of those was a lie to whoever
// looked. `<input type=range>` has no unset state — it coerces null to the
// midpoint — so the unset state has to be built rather than hoped for.
//
// Four things make it honest:
//   * the VALUE SLOT, which is what people actually read, says "Auto — Claude
//     decides" instead of a number;
//   * the track carries NO FILL while unset, because fill is the thing that
//     says "a value has been chosen up to here";
//   * the handle is hollow rather than a solid accent dot;
//   * any interaction commits, and a visible Auto button goes back — never a
//     hidden re-click.
//
// There is also a number input beside it. NN/g names age, weight and height as
// the cases where a slider is the wrong control because the exact value matters;
// the slider stays for the coarse gesture, the input for the actual number.
//
// Accessibility: with no value we omit aria-valuenow entirely — ARIA says that
// with no aria-valuenow "no information is implied about a current value" — and
// use aria-valuetext, which exists precisely for a value that cannot be
// meaningfully represented as a number.

export function RangeField({
  label, value, onChange, min, max, step = 1,
  unit = "", format, placeholder = 168, nullable = false, autoLabel = "Claude decides",
}) {
  const unset = nullable && (value === null || value === undefined || value === "");
  const shown = unset ? placeholder : Number(value);
  const pct = ((shown - min) / (max - min)) * 100;

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <label className="text-[11px] font-medium text-ink-subtle">{label}</label>
        <span className={cn("tnum text-[12px] flex items-center gap-1.5",
          unset ? "text-ink-subtle" : "text-ink")}>
          {unset ? (
            <><Sparkles className="h-3 w-3 text-amber-300/70" /> Auto — {autoLabel}</>
          ) : (
            <>
              {format ? format(Number(value)) : `${value}${unit}`}
              {nullable && (
                <button type="button" onClick={() => onChange(null)}
                  className="rounded px-1 text-[11px] text-ink-faint hover:text-ink">
                  auto
                </button>
              )}
            </>
          )}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min} max={max} step={step}
          value={shown}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={label}
          // No value means no aria-valuenow. The text carries the meaning.
          aria-valuenow={unset ? undefined : Number(value)}
          aria-valuetext={unset ? `Auto, ${autoLabel}` : `${value}${unit}`}
          className={cn("h-1.5 flex-1 cursor-pointer appearance-none rounded-full",
            "bg-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40",
            unset ? "range-unset" : "accent-rose-400")}
          style={unset ? undefined : {
            background:
              `linear-gradient(to right, rgb(251 113 133) ${pct}%, var(--line) ${pct}%)`,
          }}
        />
        <input
          type="number"
          min={min} max={max} step={step}
          value={unset ? "" : value}
          placeholder="auto"
          onChange={(e) => {
            const v = e.target.value;
            if (v === "") return onChange(nullable ? null : min);
            onChange(Math.min(max, Math.max(min, Number(v))));
          }}
          aria-label={`${label} value`}
          className={cn("tnum w-[72px] shrink-0 rounded-md bg-raised ring-1 ring-line px-2 h-8",
            "text-[13px] outline-none focus:ring-line-strong",
            unset ? "text-ink-subtle placeholder:text-ink-faint" : "text-ink")}
        />
      </div>

      <div className="tnum flex justify-between text-[11px] text-ink-faint">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

export default RangeField;
