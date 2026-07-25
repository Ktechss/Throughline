import { X, LoaderCircle, Wand2, Sparkles } from 'lucide-react'
import { DETAIL_FIELDS, OUTFIT_PICKERS } from '@/lib/eve'

// Right-side drawer for the design/describe → review → generate outfit flow.
export default function OutfitDrawer({
  open, imageUrl, describing, outfitText, setOutfitText,
  details, onDetail, creating, onGenerate, onClose,
  idea, setIdea, pickers, onPicker, enriching, onEnrich,
}) {
  if (!open) return null
  const missing = details ? DETAIL_FIELDS.filter((f) => !(details[f.key] || '').trim()).length : 0
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onMouseDown={onClose}>
      <aside className="flex h-full w-full max-w-md flex-col border-l border-[#24242e] bg-[#111117]" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#24242e] px-5 py-4">
          <h2 className="text-lg font-semibold">Outfit designer</h2>
          <button onClick={onClose} className="text-[#777785] hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {imageUrl && (
            <img src={imageUrl} alt="uploaded outfit"
              className="mb-4 max-h-72 w-full rounded-lg border border-[#24242e] object-contain bg-[#0b0b0e]" />
          )}

          {describing ? (
            <div className="flex items-center gap-3 rounded-lg border border-[#315d88] bg-[#101b27] p-4">
              <LoaderCircle className="h-5 w-5 animate-spin text-[#4ea1ff]" />
              <span className="text-sm text-[#8fb6dd]">Claude is reading the outfit…</span>
            </div>
          ) : (
            <>
              {/* Design from a short idea + structured picks — Claude expands it
                  into a rich, opaque garment description that fills the box below. */}
              <label className="eve-label">idea <span className="text-[#5f6b7a]">— a short outfit idea (optional)</span></label>
              <input value={idea || ''} onChange={(e) => setIdea(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !enriching) onEnrich() }}
                placeholder="e.g. emerald festive lehenga for a sangeet"
                className="eve-input mb-3 mt-1" />

              {OUTFIT_PICKERS.map((grp) => (
                <div key={grp.key} className="mb-2">
                  <span className="eve-label text-[#8a8a99]">{grp.label}</span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {grp.options.map((o) => {
                      const on = pickers?.[grp.key] === o
                      return (
                        <button key={o} type="button" onClick={() => onPicker(grp.key, on ? '' : o)}
                          className={`rounded-full border px-2.5 py-1 text-[11px] capitalize transition ${on
                            ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
                            : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>{o}</button>
                      )
                    })}
                  </div>
                </div>
              ))}

              <button onClick={onEnrich} disabled={enriching}
                className="eve-button mb-5 mt-3 w-full border border-[#315d88] bg-[#101b27] text-[#8fb6dd] hover:border-[#4ea1ff]">
                {enriching
                  ? <><LoaderCircle className="h-4 w-4 animate-spin" /> writing…</>
                  : <><Sparkles className="h-4 w-4" /> write outfit</>}
              </button>

              <label className="eve-label">description — edit freely</label>
              <textarea value={outfitText} onChange={(e) => setOutfitText(e.target.value)} rows={9}
                placeholder="describe the garments — top, bottom, footwear, accessories"
                className="eve-input mb-5 mt-1 resize-y leading-relaxed" />

              <div className="mb-2 flex items-center justify-between">
                <span className="eve-label text-[#edb755]">key details — fill what the photo didn’t show</span>
                {missing > 0 && <span className="eve-chip text-[#edb755]">{missing} to add</span>}
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {DETAIL_FIELDS.map((f) => {
                  const val = details?.[f.key] || ''
                  const empty = !val.trim()
                  return (
                    <label key={f.key} className="block">
                      <span className="flex items-center gap-1 text-[11px] text-[#aaaab5]">
                        {f.label}{empty && <span className="text-[#edb755]">• add</span>}
                      </span>
                      <input value={val} onChange={(e) => onDetail(f.key, e.target.value)} placeholder={f.hint}
                        className={`mt-1 h-9 w-full rounded-md border bg-[#0e0e12] px-2.5 text-xs text-[#e6e6ea] outline-none placeholder:text-[#565663] focus:border-[#4ea1ff] ${empty ? 'border-[#6a5320]' : 'border-[#30303a]'}`} />
                    </label>
                  )
                })}
              </div>
              <p className="mt-3 text-[11px] text-[#8a8a99]">These fold into the outfit — heels, nail colours (hands + feet), lipstick and lower-garment type the reference may not show.</p>
            </>
          )}
        </div>

        <div className="border-t border-[#24242e] p-4">
          <button onClick={onGenerate} disabled={describing || !!creating || !outfitText.trim()}
            className="eve-button w-full bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff]">
            <Wand2 /> generate outfit
          </button>
        </div>
      </aside>
    </div>
  )
}
