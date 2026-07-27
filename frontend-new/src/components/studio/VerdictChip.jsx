import { cn } from "@/lib/utils";

const STATUS_STYLES = {
  kept: { dot: "bg-emerald-400", text: "text-emerald-300", label: "Kept", ring: "ring-emerald-500/30" },
  rejected: { dot: "bg-rose-400", text: "text-rose-300", label: "Rejected", ring: "ring-rose-500/30" },
  other: { dot: "bg-amber-400", text: "text-amber-300", label: "Other", ring: "ring-amber-500/30" },
  ungated: { dot: "bg-zinc-500", text: "text-zinc-400", label: "Ungated", ring: "ring-zinc-500/30" },
};

export default function VerdictChip({ status, similarity, yaw, facePx, poseMismatch, className }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.ungated;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-medium", className)}>
      <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 ring-1", s.text, s.ring, "bg-white/5")}>
        <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
        {s.label}
      </span>
      {similarity != null && (
        <span className="tabular-nums text-zinc-300">
          sim <span className={poseMismatch ? "line-through opacity-50" : "text-zinc-100"}>{similarity.toFixed(2)}</span>
        </span>
      )}
      {yaw != null && (
        <span className="tabular-nums text-zinc-400">yaw {yaw > 0 ? "+" : ""}{yaw}°</span>
      )}
      {facePx != null && (
        <span className="tabular-nums text-zinc-400">{facePx}px face</span>
      )}
    </div>
  );
}