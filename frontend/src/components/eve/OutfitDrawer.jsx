import { X, LoaderCircle, Wand2, Sparkles, ImagePlus } from 'lucide-react'
import { DETAIL_FIELDS, OUTFIT_PICKERS } from '@/lib/eve'

// Right-side drawer — the single outfit builder. Two ways to fill the same
// description box: upload a reference photo (Claude describes it) OR type an idea
// + pick attributes (Claude writes it). Then review/edit → generate.
export default function OutfitDrawer({
  open, imageUrl, describing, outfitText, setOutfitText,
  details, onDetail, creating, onGenerate, onClose, onDescribe,
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
              {/* 1) Upload an outfit photo → Claude describes it into the box below. */}
              <label className="eve-label">reference photo <span className="text-[#5f6b7a]">— upload an outfit to describe</span></label>
              <label className="mb-4 mt-1 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-[#3a3a46] px-3 py-3 text-xs text-[#8a8a99] transition hover:border-[#4ea1ff] hover:text-[#cfe0f5]">
                <ImagePlus className="h-4 w-4" /> upload an outfit photo
                <input type="file" accept="image/*" hidden onChange={onDescribe} />
              </label>

              {/* 2) The outfit description — from the photo, hand-typed, or enriched. */}
              <label className="eve-label">outfit description <span className="text-[#5f6b7a]">— edit freely</span></label>
              <textarea value={outfitText} onChange={(e) => setOutfitText(e.target.value)} rows={8}
                placeholder="upload a photo above, type an outfit, then Enrich — top, bottom, footwear, accessories"
                className="eve-input mb-4 mt-1 resize-y leading-relaxed" />

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

              {/* 3) Enrich — rewrite the description above far richer/more precise,
                  optionally adapted by a tweak + attribute chips. */}
              <div className="my-4 flex items-center gap-2 text-[10px] uppercase tracking-wider text-[#565663]">
                <span className="h-px flex-1 bg-[#24242e]" /><Sparkles className="h-3 w-3" /> enrich<span className="h-px flex-1 bg-[#24242e]" />
              </div>
              <input value={idea || ''} onChange={(e) => setIdea(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !enriching) onEnrich() }}
                placeholder="optional tweak — e.g. make it silk · add embroidery · adapt to a sangeet"
                className="eve-input mb-3" />

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
                className="eve-button mt-3 w-full border border-[#315d88] bg-[#101b27] text-[#8fb6dd] hover:border-[#4ea1ff]">
                {enriching
                  ? <><LoaderCircle className="h-4 w-4 animate-spin" /> enriching…</>
                  : <><Sparkles className="h-4 w-4" /> {outfitText.trim() ? 'enrich outfit' : 'write outfit'}</>}
              </button>
              <p className="mt-2 text-[11px] text-[#8a8a99]">Enrich rewrites the description above with far richer garment detail — same outfit, adapted by any tweak/attributes. (Empty box: writes one from your tweak + attributes.)</p>
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
