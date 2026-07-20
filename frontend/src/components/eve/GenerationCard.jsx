import { LoaderCircle, AlertTriangle } from 'lucide-react'
import VerdictChips from './VerdictChips'

// v = genView(): running | error | finished runView
export default function GenerationCard({ v, onOpen }) {
  if (v.running) return (
    <article className="eve-card flex aspect-[4/5] flex-col items-center justify-center gap-4 bg-[#111117] p-4 text-center">
      <LoaderCircle className="h-6 w-6 animate-spin text-[#4ea1ff]" />
      <div>
        <p className="text-sm">{v.stage}</p>
        <p className="mt-1 font-mono text-[10px] text-[#696978]">{v.elapsed}s · {v.label}</p>
      </div>
      {v.retry ? <span className="eve-chip">moderation retry {v.retry}</span> : <span className="eve-chip">job {v.id}</span>}
    </article>
  )
  if (v.error) return (
    <article className="eve-card flex aspect-[4/5] flex-col items-center justify-center gap-3 border-[#5d2926] bg-[#211313] p-6 text-center">
      <AlertTriangle className="text-[#e2564a]" />
      <p className="text-sm text-[#f18b84]">Generation failed</p>
      <small className="text-[#9b6764]">{v.error}</small>
    </article>
  )
  return (
    <button onClick={() => onOpen(v.raw)} className="eve-card group relative overflow-hidden text-left">
      <img src={v.thumb || v.image} loading="lazy" decoding="async" alt={v.label} className="aspect-[4/5] w-full object-cover transition duration-500 group-hover:scale-[1.02]" />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-3 pt-12">
        <VerdictChips v={v} />
        <div className="mt-2 flex justify-between text-[11px]">
          <span className="truncate">{v.label}</span>
          <span className="ml-2 shrink-0 font-mono text-[#aaaab5]">{v.model}</span>
        </div>
      </div>
    </button>
  )
}
