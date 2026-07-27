import React, { useState } from "react";
import { ChevronDown, Download, Trash2, Check, X, Eraser } from "lucide-react";
import { cn } from "@/lib/utils";
import VerdictChip from "./VerdictChip";

export default function ReviewTab({ stats, shots, onOpenDetail, onMark, onDelete, onExportGold, onPurgeRejected, onCleanup }) {
  const [expanded, setExpanded] = useState(false);

  const totalShots = stats ? stats.totalShots : 0;
  const keepRate = stats ? stats.keepRate : 0;
  const approved = stats ? stats.approved : 0;
  const rejected = stats ? stats.rejected : 0;
  const goldSet = stats ? stats.goldSet : 0;

  return (
    <div className="space-y-6">
      {/* Header count */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-6">
          <Metric label="Shot images" value={totalShots} />
          <Metric label="Keep-rate" value={`${Math.round(keepRate * 100)}%`} accent="emerald" />
          <Metric label="Approved" value={approved} accent="emerald" />
          <Metric label="Rejected" value={rejected} accent="rose" />
          <Metric label="Gold set" value={goldSet} accent="amber" />
        </div>
        <div className="flex gap-2">
          <button onClick={onExportGold} className="rounded-lg ring-1 ring-white/10 hover:bg-white/5 px-3 py-2 text-[12px] text-zinc-300 flex items-center gap-1.5"><Download className="h-3.5 w-3.5" /> Export gold set</button>
          {rejected > 0 && (
            <button onClick={onPurgeRejected} className="rounded-lg ring-1 ring-rose-500/30 hover:bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300 flex items-center gap-1.5"><Trash2 className="h-3.5 w-3.5" /> Delete rejected ({rejected})</button>
          )}
          <button onClick={onCleanup} className="rounded-lg ring-1 ring-white/10 hover:bg-white/5 px-3 py-2 text-[12px] text-zinc-300 flex items-center gap-1.5"><Eraser className="h-3.5 w-3.5" /> Clean up images</button>
        </div>
      </div>

      {/* Learning stats (collapsible) */}
      {stats && (
        <div className="rounded-xl ring-1 ring-white/8 bg-white/[0.02] overflow-hidden">
          <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02]">
            <span className="text-[12px] font-medium text-zinc-300">Learning stats</span>
            <ChevronDown className={cn("h-4 w-4 text-zinc-500 transition-transform", expanded && "rotate-180")} />
          </button>
          {expanded && (
            <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 gap-6 border-t border-white/5 pt-4">
              <div>
                <h4 className="text-[11px] text-zinc-500 mb-2">Keep-rate by pose</h4>
                <div className="space-y-1.5">
                  {(stats.byPose || []).map((p) => <BarRow key={p.label} label={p.label} rate={p.rate} kept={p.kept} total={p.total} />)}
                </div>
              </div>
              <div>
                <h4 className="text-[11px] text-zinc-500 mb-2">Top recipes by outfit</h4>
                <div className="space-y-1.5">
                  {(stats.byOutfit || []).map((o) => <BarRow key={o.label} label={o.label} rate={o.rate} kept={o.kept} total={o.total} />)}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Gallery */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[13px] font-semibold text-zinc-200">Gallery</h3>
          <span className="text-[11px] text-zinc-600 tabular-nums">{shots.length} shots</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {shots.map((s) => (
            <ShotCard
              key={s.id}
              shot={s}
              onOpen={() => onOpenDetail(s)}
              onApprove={() => onMark(s.id, "approve")}
              onReject={() => onMark(s.id, "reject")}
              onDelete={() => onDelete(s.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, accent }) {
  return (
    <div>
      <div className={cn("text-xl font-semibold tabular-nums", accent === "emerald" && "text-emerald-300", accent === "rose" && "text-rose-300", accent === "amber" && "text-amber-300", !accent && "text-zinc-100")}>{value}</div>
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5">{label}</div>
    </div>
  );
}

function BarRow({ label, rate, kept, total }) {
  const pct = Math.round(rate * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-zinc-400 w-24 truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
        <div className={cn("h-full rounded-full", rate >= 0.5 ? "bg-emerald-400/70" : rate > 0 ? "bg-amber-400/70" : "bg-rose-400/70")} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-zinc-500 tabular-nums w-16 text-right">{kept}/{total} · {pct}%</span>
    </div>
  );
}

function ShotCard({ shot, onOpen, onApprove, onReject, onDelete }) {
  return (
    <div className="group rounded-xl ring-1 ring-white/8 bg-white/[0.02] overflow-hidden hover:ring-white/20 transition-all">
      <button onClick={onOpen} className="relative block w-full aspect-[4/5] overflow-hidden bg-zinc-900">
        <img src={shot.thumb} alt={shot.brief} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2.5">
          <VerdictChip status={shot.status} similarity={shot.similarity} yaw={shot.yaw} facePx={shot.facePx} />
        </div>
        <div className={cn("absolute top-2 right-2 h-2.5 w-2.5 rounded-full ring-2 ring-black/40", shot.status === "kept" ? "bg-emerald-400" : "bg-rose-400")} />
      </button>
      <div className="px-2.5 py-2">
        <div className="text-[11px] text-zinc-300 line-clamp-1">{shot.brief}</div>
        <div className="mt-1 flex items-center gap-1.5">
          <button onClick={onApprove} className={cn("flex-1 rounded-md py-1 text-[10px] font-medium flex items-center justify-center gap-1 transition-colors", shot.approved ? "bg-emerald-500/20 text-emerald-300" : "bg-white/5 text-zinc-400 hover:text-emerald-300")}>
            <Check className="h-3 w-3" /> {shot.approved ? "approved" : "approve"}
          </button>
          <button onClick={onReject} className={cn("flex-1 rounded-md py-1 text-[10px] flex items-center justify-center gap-1 transition-colors", shot.rejected ? "bg-rose-500/20 text-rose-300" : "bg-white/5 text-zinc-400 hover:text-rose-300")}>
            <X className="h-3 w-3" /> {shot.rejected ? "rejected" : "reject"}
          </button>
          <button onClick={onDelete} className="rounded-md bg-white/5 p-1.5 text-zinc-500 hover:text-rose-400"><Trash2 className="h-3 w-3" /></button>
        </div>
      </div>
    </div>
  );
}
