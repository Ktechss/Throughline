import React, { useEffect, useState } from "react";
import { api } from "@/api/throughline";
import { cn } from "@/lib/utils";

// WHICH MODEL RENDERS THIS ONE IMAGE.
//
// Not a settings-page decision, because it is not a settings-page kind of
// choice: the wardrobe turnaround and the shot that wears it are two different
// jobs with different failure modes, and the owner may reasonably want a
// different renderer for each. So the picker sits next to every generate
// button, defaulting to the project default and overriding it for one press.
//
// Measured on one project prompt, same references, scored on her own gallery:
//
//     nano-banana-pro   0.7634    seedream-4.5     0.7724
//     seedream-5-pro    0.7638    seedream-5-lite  0.6658
//
// Identity is close across all four and the numbers do NOT rank them the way
// the eye does — nano renders skin texture and hand anatomy the seedream tiers
// do not, and the gate is blind to both. That is why this control shows price
// and resolution ceiling but makes no quality claim: the only honest quality
// signal here is looking at the picture.

let _cache = null;                       // the catalogue is static per process

export function useModels() {
  const [models, setModels] = useState(_cache?.models || []);
  const [def, setDef] = useState(_cache?.default || null);

  useEffect(() => {
    let alive = true;
    api.get("/api/models")
       .then((d) => {
         _cache = d;
         if (!alive) return;
         setModels(d.models || []);
         setDef(d.default || null);
       })
       .catch(() => {});
    return () => { alive = false; };
  }, []);

  const saveDefault = async (id) => {
    const d = await api.send("/api/models", "PUT", { model: id });
    _cache = d;
    setModels(d.models || []);
    setDef(d.default);
    return d.default;
  };

  return { models, def, saveDefault };
}

/**
 * value    — model id, or null to follow the project default
 * onChange — (id | null) => void
 */
export default function ModelPicker({ value, onChange, className, label = "Model" }) {
  const { models, def } = useModels();
  if (!models.length) return null;

  const effective = value || def;
  const row = models.find((m) => m.id === effective);
  // The ceiling is the honest maximum, not the requested one. 5-pro has no 4K
  // tier, so a 4K request renders at 2K — worth saying before the shot, not
  // after, because a halved frame is what put a face under the abstain floor.
  const capped = row && row.ceiling !== "4K";

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-2">
        <span className="text-[10.5px] uppercase tracking-[.12em] text-zinc-500">{label}</span>
        {!value && (
          <span className="text-[10px] text-zinc-600">following default</span>
        )}
      </div>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="w-full rounded-lg bg-white/[0.04] ring-1 ring-line px-2.5 py-1.5
                   text-[12.5px] text-zinc-200 outline-none focus-visible:ring-emerald-500/60"
      >
        <option value="">Default — {models.find((m) => m.id === def)?.label || "—"}</option>
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label} · ${m.usd_4k.toFixed(3)} · {m.ceiling} · {m.max_refs} refs
          </option>
        ))}
      </select>
      {capped && (
        <p className="text-[10.5px] text-amber-400/90 leading-snug">
          {row.label} tops out at {row.ceiling}. A 4K request renders at {row.ceiling},
          which shrinks the face and can drop it below the gate's floor.
        </p>
      )}
    </div>
  );
}
