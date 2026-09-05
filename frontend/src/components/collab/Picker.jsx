import React from "react";
import { Lock, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const field =
  "w-full min-w-0 truncate rounded-md bg-raised ring-1 ring-line px-2.5 h-8 text-[13px] " +
  "outline-none focus:ring-line-strong text-ink-muted";

// One labelled <select> over a library.
//
// `groups` is the {group: [{id, label}]} shape /api/scene/library returns for
// every vocabulary; `flat` is the [{id, label}] shape it returns for the ones
// with no groups. Both exist server-side already, so this component never has to
// know which library it is rendering — which is the point, because there are now
// fourteen of them and a bespoke picker each would be fourteen places for a
// dropdown to quietly stop being wired up.
export default function Picker({ label, value, onChange, groups, flat, empty = "—",
                                 hint, disabled, className, auto }) {
  // AUTO IS A VALUE, NOT AN EMPTY BOX.
  //
  // Every one of these started blank and read "from brief" or "—", which cannot
  // distinguish "the system chose something for you" from "nothing happened".
  // The backend has always known what it inferred — _infer_capture returns it,
  // and it was being flattened into prose and discarded. Now the resolved value
  // is shown in the control it belongs to, with a lock to keep it.
  const resolved = !value && auto?.value ? auto.value : null;
  const optionLabel = (id) =>
    (flat || []).find((o) => o.id === id)?.label
    || Object.values(groups || {}).flat().find((o) => o.id === id)?.label
    || id;

  return (
    <label className={cn("block", className)}>
      <span className="text-[11px] font-medium text-ink-subtle flex items-center gap-1">
        {label}
        {hint && <span className="text-zinc-600">· {hint}</span>}
      </span>
      <select value={value || ""} disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={cn(field, "mt-1", disabled && "opacity-40",
          // Auto is muted; a value you chose is full contrast. The asymmetry is
          // what makes "which of these did I set?" answerable without reading.
          !value && "text-ink-subtle")}>
        <option value="">{resolved ? `Auto — ${optionLabel(resolved)}` : empty}</option>
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
      {resolved && (
        <span className="mt-1 flex items-start gap-1 text-[11px] text-ink-faint">
          <Sparkles className="h-3 w-3 shrink-0 mt-0.5 text-amber-300/70" />
          <span className="min-w-0 flex-1 truncate" title={auto.why}>
            {auto.why?.replace(/^[a-z_]+=\S+\s*/, "") || "chosen for you"}
          </span>
          <button type="button" onClick={(e) => { e.preventDefault(); onChange(resolved); }}
            title="Keep this value instead of re-deciding each run"
            className="shrink-0 inline-flex items-center gap-0.5 rounded px-1 text-ink-subtle hover:text-ink">
            <Lock className="h-2.5 w-2.5" /> keep
          </button>
        </span>
      )}
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
            <div className="text-[11px] uppercase tracking-wide text-zinc-600">{g}</div>
            <div className="flex flex-wrap gap-1 mt-0.5">
              {items.map((o) => (
                <button key={o.id} type="button" onClick={() => toggle(o.id)}
                  title={o.text}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] ring-1 transition-colors",
                    has(o.id)
                      ? "bg-white text-black ring-white"
                      : "ring-line text-zinc-400 hover:ring-white/30")}>
                  {o.label}
                  {/* Face-worn items are marked because they are an identity
                      decision, not a styling one: ArcFace reads hardest on the
                      eye region and dark lenses remove it entirely. */}
                  {o.face && <span className="ml-1 text-[11px] opacity-60">◐</span>}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
