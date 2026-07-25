import { X, Check, Ban } from 'lucide-react'
import VerdictChips from './VerdictChips'
import PoseIcon from './PoseIcon'
import { ep, runView } from '@/lib/eve'

export default function OriginModal({ run, wardrobe, poseRefs, poseLibrary, onClose, onMark, onToWardrobe, onToPoseRef, onUsePose, stamp }) {
  if (!run) return null
  const v = runView(run)
  const m = run.meta || {}
  const face = (m.bio_references || [])[0]
  const outfitFile = wardrobe.find((w) => w.id === m.wardrobe)?.file
  const poseFile = poseRefs.find((w) => w.id === m.pose_ref)?.file
  const pose = (poseLibrary || []).find((p) => p.id === m.pose_id)
  const hide = (e) => { const f = e.target.closest('figure'); if (f) f.style.display = 'none' }
  const kv = [
    ['model', ep(run.endpoint)],
    ['prompt by', m.ai_prompt ? 'AI / Claude' : 'template'],
    ...(m.body ? [['body type', m.body]] : []),
    ['seed', run.seed ?? 'random'],
    ['aspect', run.aspect],
    ['time', `${run.seconds} sec`],
    ['created', (run.created || '').replace('T', ' ')],
  ]
  return (
    <div onMouseDown={onClose} className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 p-4 backdrop-blur-sm">
      <div onMouseDown={(e) => e.stopPropagation()}
        className="my-4 grid w-full max-w-5xl overflow-hidden rounded-xl border border-[#30303b] bg-[#14141a] md:grid-cols-[.9fr_1.1fr]">
        <div className="bg-[#09090b] p-4">
          <img src={v.image} className="mx-auto max-h-[65vh] rounded-md object-contain" alt={v.label} />
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button onClick={() => onMark(run.id, 'approve')} className={`eve-button ${run.mark === 'approve' ? 'bg-[#1f5a41]' : 'bg-[#173a2c]'} text-[#62d99d]`}><Check /> approve</button>
            <button onClick={() => onMark(run.id, 'reject')} className={`eve-button ${run.mark === 'reject' ? 'bg-[#5a2b29]' : 'bg-[#40201f]'} text-[#f17b72]`}><Ban /> reject</button>
            <button onClick={() => onToWardrobe(run.id)} className="eve-button border border-[#353541]">→ wardrobe</button>
            <button onClick={() => onToPoseRef(run.id)} className="eve-button border border-[#353541]">→ pose ref</button>
          </div>
        </div>
        <div className="relative overflow-y-auto p-6">
          <button onClick={onClose} className="absolute right-4 top-4 text-[#777785] hover:text-white"><X /></button>
          <p className="eve-label">origin / {run.id}</p>
          <h2 className="mt-2 text-xl font-semibold">{v.label}</h2>
          <div className="mt-3"><VerdictChips v={v} /></div>
          {v.status && run.verdict?.reason && <p className="mt-2 text-[11px] text-[#d99a2b]">{run.verdict.reason}</p>}
          {run.moderation_fallback && <p className="mt-2 text-[11px] text-[#d99a2b]">served by the scene model (weaker identity) after a moderation refusal</p>}
          <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded border border-[#24242e] bg-[#24242e] text-xs sm:grid-cols-3">
            {kv.map((x) => (
              <div key={x[0]} className="bg-[#111117] p-3">
                <span className="block text-[9px] uppercase tracking-wider text-[#666674]">{x[0]}</span>
                <span className="mt-1 block truncate font-mono">{x[1]}</span>
              </div>
            ))}
          </div>
          {m.brief && <><p className="eve-label mt-6">brief</p><p className="mt-2 text-sm text-[#b5b5bf]">{m.brief}</p></>}

          {(m.pose_id || m.pose_ref) && (
            <>
              <p className="eve-label mt-6">pose used</p>
              <div className="mt-2 flex items-center gap-3 rounded-lg border border-[#24242e] bg-[#0e0e12] p-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-[#2a2a34] text-[#9fd0ff]">
                  <PoseIcon id={m.pose_id || 'stand'} category={pose?.category} className="h-8 w-8" />
                </div>
                <div className="min-w-0 flex-1">
                  {m.pose_id
                    ? <p className="text-sm text-[#e6e6ea]">{m.pose_id}{pose?.category && <span className="ml-2 text-[10px] text-[#5f6b7a]">{pose.category}</span>}</p>
                    : <p className="text-sm text-[#e6e6ea]">custom pose reference</p>}
                  {pose?.text && <p className="mt-0.5 text-[11px] leading-relaxed text-[#8a8a99]">{pose.text}</p>}
                  {m.pose_ref && <p className="mt-0.5 text-[11px] text-[#8a8a99]">pose reference image: {m.pose_ref}</p>}
                </div>
                {onUsePose && <button onClick={() => onUsePose(run)}
                  className="eve-button shrink-0 border border-[#315d88] bg-[#101b27] text-[#8fb6dd] hover:border-[#4ea1ff]">use this pose</button>}
              </div>
            </>
          )}

          <p className="eve-label mt-6">full prompt sent</p>
          <div className="mt-2 whitespace-pre-wrap break-words rounded border border-dashed border-[#30303a] bg-[#0e0e12] p-3 font-mono text-[11px] leading-relaxed text-[#91919e]">{run.prompt}</div>
          {m.sanitised?.length > 0 && (
            <div className="mt-3 rounded border border-[#315d88] bg-[#101b27] p-3 text-[11px] text-[#8fb6dd]">
              sanitised {m.sanitised.length} phrase{m.sanitised.length > 1 ? 's' : ''}:
              <ul className="mt-1 space-y-1">
                {m.sanitised.map((c, i) => <li key={i} className="font-mono"><span className="text-[#f17b72]">{c.was}</span> → <span className="text-[#62d99d]">{c.now}</span></li>)}
              </ul>
            </div>
          )}
          <p className="eve-label mt-6">references used</p>
          <div className="mt-2 flex flex-wrap gap-3">
            {face && <figure className="m-0 w-24"><img src={`/api/refs/${face}/file?t=${stamp}`} onError={hide} className="h-28 w-24 rounded object-cover" alt="face" /><figcaption className="mt-1 truncate text-[9px] text-[#777785]">face · {face}</figcaption></figure>}
            {outfitFile && <figure className="m-0 w-24"><img src={`/api/wardrobe/${outfitFile}/file?t=${stamp}`} onError={hide} className="h-28 w-24 rounded object-cover" alt="outfit" /><figcaption className="mt-1 truncate text-[9px] text-[#777785]">outfit · {m.wardrobe}</figcaption></figure>}
            {poseFile && <figure className="m-0 w-24"><img src={`/api/pose-refs/${poseFile}/file?t=${stamp}`} onError={hide} className="h-28 w-24 rounded object-cover" alt="pose" /><figcaption className="mt-1 truncate text-[9px] text-[#777785]">pose · {m.pose_ref}</figcaption></figure>}
          </div>
          <p className="mt-2 font-mono text-[10px] text-[#565663]">attached in order: {(run.refs || []).join(' → ') || 'none'}</p>
        </div>
      </div>
    </div>
  )
}
