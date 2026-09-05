import React from "react";
import { cn } from "@/lib/utils";

// One number and what it means. Promoted out of ReviewTab's local `Metric` so
// the landing dashboard reports a character with the same vocabulary the Review
// tab already uses — the same figure should not be styled two ways in one app.

const ACCENT = {
  emerald: "text-emerald-400",
  rose: "text-rose-400",
  amber: "text-amber-400",
  zinc: "text-zinc-100",
};

export function StatTile({ label, value, accent = "zinc", hint, className }) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className={cn("text-[19px] font-semibold tabular-nums leading-none",
        ACCENT[accent] || ACCENT.zinc)}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-zinc-500 truncate">{label}</div>
      {hint && <div className="text-[10px] text-zinc-600 truncate">{hint}</div>}
    </div>
  );
}

export default StatTile;
