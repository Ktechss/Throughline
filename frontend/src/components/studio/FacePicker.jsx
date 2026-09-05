import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Modal, Button } from "@/components/ui/modal";

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
    <Modal
      open
      // Choosing her face is mandatory, so the backdrop must not dismiss it —
      // and never while the choice is being saved.
      onClose={busy ? undefined : onCancel}
      closeOnBackdrop={false}
      title={`Choose ${character.name}\u2019s face`}
      subtitle="Every future image of her descends from the one you pick."
      size="lg"
    >
      <p className="text-[11px] text-zinc-500 leading-relaxed mb-4">
        It becomes her identity reference and her calibration seed. She can&rsquo;t be
        photographed until you choose.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {candidates.map((c) => (
            <button
              key={idOf(c)}
              onClick={() => !busy && setSel(idOf(c))}
              className={cn(
                "relative rounded-xl overflow-hidden ring-1 transition-all aspect-[3/4]",
                sel === idOf(c)
                  ? "ring-2 ring-emerald-400 scale-[1.02]"
                  : "ring-line hover:ring-white/30 opacity-80 hover:opacity-100"
              )}
            >
              <img src={`/api/images/${c.file}/thumb`} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
      </div>
      <p className="mt-4 text-[11px] text-zinc-500">
        Her body reference is generated from this face, so the two agree.
      </p>
      <div className="mt-4 flex items-center justify-end gap-2">
        {onCancel && (
          <Button variant="outline" onClick={() => !busy && onCancel()} disabled={!!busy}>
            Later
          </Button>
        )}
        <Button variant="primary" onClick={() => sel && onChoose(character, sel)}
          disabled={!sel || !!busy}>
          {busy ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> {busy}</> : "Lock this face"}
        </Button>
      </div>
    </Modal>
  );
}
