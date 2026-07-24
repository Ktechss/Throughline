import { useState } from 'react'
import { Check, Ban, ScanSearch, Sparkles, Download, ChevronDown, Trash2 } from 'lucide-react'
import { runView } from '@/lib/eve'

// A recipe row: keep-rate + approve count for a pose or outfit, so you learn what
// works. Bar coloured by keep-rate.
function RecipeRow({ e }) {
  const pct = Math.round(e.keep_rate * 100)
  const col = pct >= 70 ? '#33c07f' : pct >= 50 ? '#d9a52b' : '#e2564a'
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-24 shrink-0 truncate font-mono text-[#b8b8c3]">{e.key}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-[#1a1a22]">
        <div className="h-full rounded" style={{ width: `${pct}%`, background: col }} />
      </div>
      <span className="w-20 shrink-0 text-right font-mono text-[#8a8a99]">{pct}% · {e.approved}✓/{e.n}</span>
    </div>
  )
}

// Compact per-image verdict dot + score.
function Dot({ v }) {
  const c = v.status === 'kept' ? '#33c07f' : v.status === 'rejected' ? '#e2564a'
    : v.status === 'abstain' ? '#d9a52b' : '#666674'
  return (
    <span className="flex items-center gap-1 font-mono text-[9px] text-[#8a8a99]">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
      {v.similarity != null ? v.similarity.toFixed(2) : (v.status || '—')}
    </span>
  )
}

export default function Review({ runs, onOpen, onMark, onDelete, stats, onExportGold, onPurgeRejected }) {
  const [open, setOpen] = useState(false)   // stats panel collapsed by default
  // Only actual SHOTS — hide wardrobe/body/calibration generations. One flat grid,
  // latest first (runs already newest-first).
  const shots = runs.filter((r) => {
    const m = r.meta || {}
    return !m.outfit_create && !m.body_ref_create && !m.calibrate
  })
  return (
    <main className="mx-auto max-w-[1360px] px-5 py-6">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <p className="eve-label">permanent archive</p>
          <h1 className="mt-1.5 text-2xl font-semibold">Review</h1>
        </div>
        <span className="font-mono text-[10px] text-[#777785]">{shots.length} images</span>
      </div>

      {/* Compact learning bar — one line, expandable. Approvals build the gold set
          and the recipe stats; the gallery stays frozen. */}
      {stats && stats.total > 0 && (
        <section className="mb-6 rounded-lg border border-[#24242e] bg-[#0f0f14]">
          <button onClick={() => setOpen((o) => !o)}
            className="flex w-full flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2.5 text-left">
            <span className="flex items-center gap-2 eve-label text-[#67aff8]"><Sparkles className="h-3.5 w-3.5" /> learning</span>
            <span className="font-mono text-[11px] text-[#8a8a99]">{stats.total} shots</span>
            <span className="font-mono text-[11px] text-[#33c07f]">gate keep {Math.round(stats.gate.keep_rate * 100)}%</span>
            <span className="font-mono text-[11px] text-[#62d99d]">✓{stats.marks.approved}</span>
            <span className="font-mono text-[11px] text-[#f17b72]">✕{stats.marks.rejected}</span>
            <span className="font-mono text-[11px] text-[#8a8a99]">gold {stats.gold_set}</span>
            <ChevronDown className={`ml-auto h-4 w-4 text-[#777785] transition ${open ? 'rotate-180' : ''}`} />
          </button>

          {open && (
            <div className="border-t border-[#24242e] p-4">
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <p className="eve-label mb-2">keep-rate by pose</p>
                  <div className="space-y-1.5">{(stats.by_pose || []).slice(0, 8).map((e) => <RecipeRow key={e.key} e={e} />)}</div>
                </div>
                <div>
                  <p className="eve-label mb-2">keep-rate by outfit</p>
                  <div className="space-y-1.5">{(stats.by_outfit || []).slice(0, 8).map((e) => <RecipeRow key={e.key} e={e} />)}</div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[#24242e] pt-3">
                <span className="text-xs text-[#e6e6ea]"><b>{stats.gold_set}</b> approved in gold set{stats.gold_on_disk ? ` · ${stats.gold_on_disk} exported` : ''}</span>
                <button onClick={onExportGold} className="eve-button border border-[#353541]"><Download className="h-3.5 w-3.5" /> export gold set</button>
                {stats.marks.rejected > 0 && (
                  <button onClick={onPurgeRejected} className="eve-button border border-[#5d2926] text-[#f18b84]"><Trash2 className="h-3.5 w-3.5" /> delete {stats.marks.rejected} rejected</button>
                )}
                <span className="ml-auto max-w-md text-right text-[10px] text-[#686876]">Your future LoRA dataset. Approvals never touch the gallery — it stays frozen so scores stay honest.</span>
              </div>
            </div>
          )}
        </section>
      )}

      {!shots.length && <p className="text-xs text-[#767684]">No shots yet.</p>}

      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5 2xl:grid-cols-6">
        {shots.map((r) => {
          const v = runView(r)
          const marked = r.mark
          return (
            <article key={r.id}
              className={`eve-card group relative overflow-hidden ${marked === 'approve' ? 'ring-1 ring-[#33c07f]' : marked === 'reject' ? 'ring-1 ring-[#e2564a] opacity-60' : ''}`}>
              <button onClick={() => onOpen(r)} className="block w-full">
                <img src={v.thumb} loading="lazy" decoding="async" className="aspect-[3/4] w-full object-cover transition group-hover:scale-[1.03]" alt={v.label} />
              </button>
              <button onClick={() => onDelete(r)} title="delete image"
                className="absolute left-1.5 top-1.5 z-10 rounded bg-black/60 p-1 text-[#e2564a] opacity-0 transition hover:bg-black/85 group-hover:opacity-100">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
              {marked && (
                <span className={`absolute right-1.5 top-1.5 rounded-full p-0.5 ${marked === 'approve' ? 'bg-[#33c07f] text-black' : 'bg-[#e2564a] text-black'}`}>
                  {marked === 'approve' ? <Check className="h-3 w-3" /> : <Ban className="h-3 w-3" />}
                </span>
              )}
              <div className="flex items-center gap-1.5 px-2 py-1.5">
                <Dot v={v} />
                <button onClick={() => onMark(r.id, 'approve')}
                  className={`ml-auto ${marked === 'approve' ? 'text-[#33c07f]' : 'text-[#565663] hover:text-[#33c07f]'}`}><Check className="h-3.5 w-3.5" /></button>
                <button onClick={() => onMark(r.id, 'reject')}
                  className={marked === 'reject' ? 'text-[#e2564a]' : 'text-[#565663] hover:text-[#e2564a]'}><Ban className="h-3.5 w-3.5" /></button>
                <button onClick={() => onOpen(r)} className="text-[#565663] hover:text-[#4ea1ff]"><ScanSearch className="h-3.5 w-3.5" /></button>
              </div>
            </article>
          )
        })}
      </div>
    </main>
  )
}
