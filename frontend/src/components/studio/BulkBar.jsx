import React from "react";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";

// A hover-reveal checkbox to overlay on a grid tile. `active` forces it visible
// (once anything is selected, all boxes show). Stop propagation so ticking a tile
// doesn't also open its detail view.
export function TileCheckbox({ checked, active, onChange, className }) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); onChange?.(); }}
      className={cn(
        "absolute top-2 left-2 z-10 h-5 w-5 rounded-md ring-1 flex items-center justify-center transition-all",
        checked ? "bg-white text-black ring-white"
                : "bg-black/50 text-transparent ring-white/40 hover:ring-white",
        checked || active ? "opacity-100" : "opacity-0 group-hover:opacity-100",
        className,
      )}
      aria-label={checked ? "Deselect" : "Select"}
    >
      <Check className="h-3.5 w-3.5" strokeWidth={3} />
    </button>
  );
}

// Sticky bulk-action toolbar. Shows only when count > 0.
// actions: [{ label, onClick, danger?, disabled? }]
export default function BulkBar({ count, total, onSelectAll, onCancel, actions = [] }) {
  if (!count) return null;
  return (
    <div className="sticky bottom-3 z-20 mx-auto flex w-fit items-center gap-2 rounded-xl border border-white/10 bg-[#141416]/95 px-3 py-2 shadow-xl backdrop-blur">
      <span className="text-[12px] text-zinc-300 tabular-nums px-1">{count} selected</span>
      {onSelectAll && total != null && (
        <button onClick={onSelectAll} className="text-[11px] text-zinc-400 hover:text-white px-1.5">
          {count === total ? "clear" : `select all ${total}`}
        </button>
      )}
      <span className="mx-0.5 h-4 w-px bg-white/10" />
      {actions.map((a) => (
        <button
          key={a.label}
          onClick={a.onClick}
          disabled={a.disabled}
          className={cn(
            "rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors disabled:opacity-40",
            a.danger ? "bg-rose-500/90 text-white hover:bg-rose-500"
                     : "bg-white/10 text-zinc-100 hover:bg-white/20",
          )}
        >
          {a.label}
        </button>
      ))}
      <button onClick={onCancel} className="ml-0.5 text-zinc-400 hover:text-white p-1" aria-label="Cancel">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
