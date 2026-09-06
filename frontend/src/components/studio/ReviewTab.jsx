import React, { useMemo, useState } from "react";
import { ChevronDown, Download, Trash2, Check, X, Eraser, Film } from "lucide-react";
import { Chip } from "@/components/ui/chip";
import { cn } from "@/lib/utils";
import { Z } from "@/lib/z";
import VerdictChip from "./VerdictChip";
import BulkBar, { TileCheckbox } from "./BulkBar";
import { useSelection } from "@/lib/useSelection";
import { StatTile } from "@/components/ui/stat";

export default function ReviewTab({ stats, shots, onOpenDetail, onMark, onDelete, onExportGold, onPurgeRejected, onCleanup, onBulkDelete, onBulkMark }) {
  const [expanded, setExpanded] = useState(false);
  const sel = useSelection();
  const runBulk = async (fn) => { await fn(); sel.clear(); };

  // TRIAGE, not a wall.
  //
  // This rendered every run at once: 208 cards, a 21,000px page, and no way to
  // ask the only question the tab exists to answer — "what still needs marking?"
  // 170 of these are unmarked, and finding them meant scrolling past the 38 that
  // are done.
  const [filter, setFilter] = useState("all");
  const [shown, setShown] = useState(60);

  const counts = useMemo(() => ({
    all: shots.length,
    unmarked: shots.filter((s) => !s.approved && !s.rejected).length,
    approved: shots.filter((s) => s.approved).length,
    rejected: shots.filter((s) => s.rejected).length,
    kept: shots.filter((s) => s.status === "kept").length,
    clips: shots.filter((s) => s.kind === "video").length,
  }), [shots]);

  const visible = useMemo(() => {
    const f = {
      all: () => true,
      unmarked: (s) => !s.approved && !s.rejected,
      approved: (s) => s.approved,
      rejected: (s) => s.rejected,
      kept: (s) => s.status === "kept",
      clips: (s) => s.kind === "video",
    }[filter] || (() => true);
    return shots.filter(f);
  }, [shots, filter]);

  const page = visible.slice(0, shown);
  const pick = (id) => { setFilter(id); setShown(60); };

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
          <StatTile label="Shot images" value={totalShots} />
          <StatTile label="Keep-rate" value={`${Math.round(keepRate * 100)}%`} accent="emerald" />
          <StatTile label="Approved" value={approved} accent="emerald" />
          <StatTile label="Rejected" value={rejected} accent="rose" />
          <StatTile label="Gold set" value={goldSet} accent="amber" />
        </div>
        <div className="flex gap-2">
          <button onClick={onExportGold} className="rounded-lg ring-1 ring-line hover:bg-white/5 px-3 py-2 text-[12px] text-zinc-300 flex items-center gap-1.5"><Download className="h-3.5 w-3.5" /> Export gold set</button>
          {rejected > 0 && (
            <button onClick={onPurgeRejected} className="rounded-lg ring-1 ring-rose-500/30 hover:bg-rose-500/10 px-3 py-2 text-[12px] text-rose-300 flex items-center gap-1.5"><Trash2 className="h-3.5 w-3.5" /> Delete rejected ({rejected})</button>
          )}
          <button onClick={onCleanup} className="rounded-lg ring-1 ring-line hover:bg-white/5 px-3 py-2 text-[12px] text-zinc-300 flex items-center gap-1.5"><Eraser className="h-3.5 w-3.5" /> Clean up images</button>
        </div>
      </div>

      {/* Learning stats (collapsible) */}
      {stats && (
        <div className="rounded-xl ring-1 ring-line-subtle bg-surface overflow-hidden">
          <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface">
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
        {/* Counts in the chip, omitted at zero — a filter that leads to an empty
            grid is a dead end you only discover by clicking it. */}
        {/* On the ladder (lib/z.js), not a literal. This bar and each tile's
            checkbox both sat at z-10 in the ROOT stacking context — the tile's
            `relative` parent has no z-index, so its z-10 child escaped into the
            root and tied the bar, then won on document order. Checkboxes
            painted over the chips while scrolling. Fixed from both ends: the
            bar takes the sticky rung, and the card isolates below. */}
        <div style={{ zIndex: Z.sticky }}
          className="sticky top-14 -mx-1 mb-3 flex items-center gap-1.5 overflow-x-auto no-scrollbar bg-canvas/95 px-1 py-2 backdrop-blur">
          {[
            ["unmarked", "Unmarked"], ["all", "All"], ["kept", "Past the gate"],
            ["approved", "Approved"], ["rejected", "Rejected"], ["clips", "Clips"],
          ].map(([id, label]) => (
            counts[id] > 0 || id === "all" ? (
              <Chip key={id} selected={filter === id} onClick={() => pick(id)}
                className="shrink-0 normal-case">
                {label} <span className="tnum opacity-60">{counts[id]}</span>
              </Chip>
            ) : null
          ))}
          <span className="tnum ml-auto shrink-0 pl-3 text-[11px] text-ink-faint">
            showing {Math.min(shown, visible.length)} of {visible.length}
          </span>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-6 gap-3">
          {page.map((s) => (
            <ShotCard
              key={s.id}
              shot={s}
              selected={sel.has(s.id)}
              selecting={sel.count > 0}
              onToggleSelect={() => sel.toggle(s.id)}
              onOpen={() => onOpenDetail(s)}
              onApprove={() => onMark(s.id, "approve")}
              onReject={() => onMark(s.id, "reject")}
              onDelete={() => onDelete(s.id)}
            />
          ))}
        </div>

        {visible.length > page.length && (
          <div className="mt-4 flex justify-center">
            <button onClick={() => setShown((n) => n + 60)}
              className="h-9 rounded-md bg-surface ring-1 ring-line px-4 text-[13px] text-ink-muted hover:bg-raised">
              Load {Math.min(60, visible.length - page.length)} more
            </button>
          </div>
        )}
        {visible.length === 0 && (
          <div className="rounded-xl bg-surface ring-1 ring-line-subtle py-12 text-center text-[13px] text-ink-subtle">
            Nothing here — every shot in this view has been marked.
          </div>
        )}
      </div>

      {/* Bulk actions apply to what is ON SCREEN, so "select all" cannot
          silently reach 208 rows while you are looking at 60. */}
      <BulkBar
        count={sel.count}
        total={page.length}
        onSelectAll={() => sel.selectAll(page.map((s) => s.id))}
        onCancel={sel.clear}
        actions={[
          { label: "Approve", onClick: () => runBulk(() => onBulkMark(sel.ids, "approve")) },
          { label: "Reject", onClick: () => runBulk(() => onBulkMark(sel.ids, "reject")) },
          { label: `Delete ${sel.count}`, danger: true, onClick: () => runBulk(() => onBulkDelete(sel.ids)) },
        ]}
      />
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

function ShotCard({ shot, selected, selecting, onToggleSelect, onOpen, onApprove, onReject, onDelete }) {
  return (
    /* `isolate` makes this card its own stacking context, so the checkbox and
       every other overlay inside it stack against the CARD instead of escaping
       into the root and competing with page chrome. */
    <div className={cn("group isolate rounded-xl ring-1 bg-surface overflow-hidden transition-all", selected ? "ring-white/60" : "ring-line-subtle hover:ring-white/20")}>
      <button onClick={selecting ? onToggleSelect : onOpen} className="relative block w-full aspect-[4/5] overflow-hidden bg-zinc-900">
        <TileCheckbox checked={selected} active={selecting} onChange={onToggleSelect} />
        <img src={shot.thumb} alt={shot.brief} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
        {/* A clip's thumb is its first frame, so without this it is indistinguishable
            from the still it was animated from. */}
        {shot.kind === "video" && (
          <div className="absolute top-2 left-2 flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] font-medium text-zinc-200 ring-1 ring-white/15">
            <Film className="h-2.5 w-2.5" />{shot.duration ? `${shot.duration}s` : "clip"}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2.5">
          <VerdictChip status={shot.status} pov={shot.pov} similarity={shot.similarity} yaw={shot.yaw} facePx={shot.facePx} />
        </div>
        <div className={cn("absolute top-2 right-2 h-2.5 w-2.5 rounded-full ring-2 ring-black/40", shot.pov ? "bg-indigo-400" : shot.status === "kept" ? "bg-emerald-400" : "bg-rose-400")} />
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
