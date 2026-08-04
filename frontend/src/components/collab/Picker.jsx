import React from "react";
import { cn } from "@/lib/utils";

const field =
  "w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] " +
  "outline-none focus:ring-white/30 text-zinc-200";

// One labelled <select> over a library.
//
// `groups` is the {group: [{id, label}]} shape /api/scene/library returns for
// every vocabulary; `flat` is the [{id, label}] shape it returns for the ones
// with no groups. Both exist server-side already, so this component never has to
// know which library it is rendering — which is the point, because there are now
// fourteen of them and a bespoke picker each would be fourteen places for a
// dropdown to quietly stop being wired up.
export default function Picker({ label, value, onChange, groups, flat, empty = "—",
                                 hint, disabled, className }) {
  return (
    <label className={cn("block", className)}>
      <span className="text-[10px] text-zinc-500 flex items-center gap-1">
        {label}
        {hint && <span className="text-zinc-600">· {hint}</span>}
      </span>
      <select value={value || ""} disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={cn(field, "mt-1", disabled && "opacity-40")}>
        <option value="">{empty}</option>
        {flat?.map((o) => (
          <option key={o.id} value={o.id}>{o.label || o.id}</option>
        ))}
        {groups && Object.entries(groups).map(([g, items]) => (
          <optgroup key={g} label={g}>
            {items.map((o) => (
              <option key={o.id} value={o.id}>{o.label || o.id}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

// Multi-select as toggling chips. Used for accessories, where "sunglasses AND
// hoops AND a crossbody" is the normal case and a <select multiple> is a
// famously bad way to express it.
export function ChipMulti({ label, values = [], onChange, groups, hint }) {
  const has = (id) => values.includes(id);
  const toggle = (id) =>
    onChange(has(id) ? values.filter((v) => v !== id) : [...values, id]);

  return (
    <div>
      <span className="text-[10px] text-zinc-500 flex items-center gap-1">
        {label}
        {hint && <span className="text-zinc-600">· {hint}</span>}
      </span>
      <div className="mt-1 space-y-1.5 max-h-40 overflow-y-auto pr-1">
        {Object.entries(groups || {}).map(([g, items]) => (
          <div key={g}>
            <div className="text-[9px] uppercase tracking-wide text-zinc-600">{g}</div>
            <div className="flex flex-wrap gap-1 mt-0.5">
              {items.map((o) => (
                <button key={o.id} type="button" onClick={() => toggle(o.id)}
                  title={o.text}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] ring-1 transition-colors",
                    has(o.id)
                      ? "bg-white text-black ring-white"
                      : "ring-white/10 text-zinc-400 hover:ring-white/30")}>
                  {o.label}
                  {/* Face-worn items are marked because they are an identity
                      decision, not a styling one: ArcFace reads hardest on the
                      eye region and dark lenses remove it entirely. */}
                  {o.face && <span className="ml-1 text-[8px] opacity-60">◐</span>}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
