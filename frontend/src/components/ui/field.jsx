import React from "react";
import { cn } from "@/lib/utils";

// Label over control, with an optional hint underneath. Landing repeats this
// shape inline six times and AnimatePanel.jsx:408 keeps a private copy; the only
// differences between them were padding and text size, none of them deliberate.

export function Field({ label, hint, required, children, className }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-[11px] text-zinc-400">
          {label}
          {required && <span className="text-rose-400"> *</span>}
        </label>
      )}
      {children}
      {hint && <p className="text-[10px] text-zinc-600 leading-relaxed">{hint}</p>}
    </div>
  );
}

// The input styling that was pasted into four places in Landing alone, and which
// components/collab/Picker.jsx:4 already kept as a private `field` const.
export const inputClass =
  "w-full rounded-lg bg-white/5 ring-1 ring-line px-3 py-2 text-[13px] " +
  "text-zinc-200 placeholder:text-zinc-600 outline-none focus:ring-white/30";

export default Field;
