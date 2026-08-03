import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// The one judgement this project deliberately leaves to a human. Everything else
// about identity is a number — "is this still her?" is measured, never eyeballed
// — but WHO SHE IS is a choice, and it is made exactly once.
//
// It is also MANDATORY, which is why this lives in its own file rather than
// inside the create flow: a character with no master face cannot be photographed
// at all (shot() refuses on the missing reference), so letting anyone into her
// studio before choosing would only hand them a dead end. Both the roster and
// the studio route here instead.
export default function FacePicker({ character, candidates, onChoose, busy, onCancel }) {
  const [sel, setSel] = useState(candidates[0]?.run_id || candidates[0]?.id || null);
  const idOf = (c) => c.run_id || c.id;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => !busy && onCancel?.()} />
      <div className="relative w-full max-w-3xl rounded-2xl bg-[#0d0d0f] ring-1 ring-white/10 overflow-hidden">
        <div className="px-6 py-5 border-b border-white/5">
          <h3 className="text-[15px] font-semibold">Choose {character.name}&rsquo;s face</h3>
          <p className="text-[11px] text-zinc-500 mt-1 leading-relaxed">
            Every future image of her descends from the one you pick — it becomes her identity
            reference and her calibration seed. She can&rsquo;t be photographed until you choose.
          </p>
        </div>

        <div className="p-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {candidates.map((c) => (
            <button
              key={idOf(c)}
              onClick={() => !busy && setSel(idOf(c))}
              className={cn(
                "relative rounded-xl overflow-hidden ring-1 transition-all aspect-[3/4]",
                sel === idOf(c)
                  ? "ring-2 ring-emerald-400 scale-[1.02]"
                  : "ring-white/10 hover:ring-white/30 opacity-80 hover:opacity-100"
              )}
            >
              <img src={`/api/images/${c.file}/thumb`} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>

        <div className="px-6 py-4 border-t border-white/5 flex items-center gap-3">
          <p className="flex-1 text-[11px] text-zinc-500">
            Her body reference is generated from this face, so the two agree.
          </p>
          {onCancel && (
            <button onClick={() => !busy && onCancel()} disabled={!!busy}
              className="rounded-lg ring-1 ring-white/10 px-4 py-2.5 text-[13px] text-zinc-400 hover:bg-white/5 disabled:opacity-40">
              Later
            </button>
          )}
          <button
            onClick={() => sel && onChoose(character, sel)}
            disabled={!sel || !!busy}
            className="rounded-lg bg-white text-black px-5 py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-2"
          >
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> {busy}</> : "Lock this face"}
          </button>
        </div>
      </div>
    </div>
  );
}
