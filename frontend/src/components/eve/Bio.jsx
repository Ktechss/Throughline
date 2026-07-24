import { useState } from 'react'
import { Star, Trash2, LoaderCircle, ImagePlus, X } from 'lucide-react'

export default function Bio({
  bio, refs, parts, importPath, setImportPath,
  onImport, onUploadRef, onSetBio, onToGallery, onDeleteRef, savePart, onResetParts,
  bodyCreating, bodyPreview, stamp, bodies = [], onSelectBody, onDeleteBody,
  onCreateBody, onUploadShape, onSaveBody, onDiscardBody,
}) {
  const [view, setView] = useState('overview')
  const [shapeRef, setShapeRef] = useState(null)   // optional body-shape reference for the next body-ref generation
  const [figure, setFigure] = useState('')         // explicit figure text for the body-ref generation (curvy control)
  const sections = [...new Set(parts.map((p) => p.section))]
  const uploadShape = async (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    if (!f || !onUploadShape) return
    try { const info = await onUploadShape(f); if (info?.name) setShapeRef(info.name) } catch { /* handled upstream */ }
  }

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-7">
      <div className="mb-6 flex flex-wrap gap-5 border-b border-[#24242e]">
        {['overview', 'advanced · face', 'advanced · body', 'advanced · parts'].map((x) => (
          <button key={x} onClick={() => setView(x)}
            className={`pb-3 text-xs ${view === x ? 'border-b border-[#4ea1ff] text-white' : 'text-[#747482]'}`}>{x}</button>
        ))}
      </div>

      {view === 'overview' && (
        <div className="grid gap-5 md:grid-cols-[280px_1fr]">
          <div className="eve-card overflow-hidden">
            {bio?.reference && <img src={`/api/refs/${bio.reference}/file?t=${stamp}`} className="aspect-[4/5] w-full object-cover" alt="identity" />}
            <div className="p-3">
              <p className="eve-label text-[#4ea1ff]">identity lock</p>
              <p className="mt-2 text-xs leading-relaxed text-[#9999a5]">{bio?.identity_lock}</p>
            </div>
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Eve identity system</h1>
            <p className="mt-2 text-sm text-[#8a8a99]">
              Gate threshold {bio?.gallery?.threshold ?? '—'} · {bio?.gallery?.entries?.length || 0} gallery angles active
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {(bio?.gallery?.entries || []).map((e) => {
                const y = bio.gallery.meta?.[e]?.yaw
                return <span key={e} className="eve-chip">{e} {y > 0 ? '+' : ''}{y?.toFixed?.(0) ?? 0}°</span>
              })}
            </div>
            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {Object.entries(bio?.sections || {}).flatMap(([sec, ps]) => ps.map((p) => (
                <div key={p.id} className="rounded-lg border border-dashed border-[#30303a] p-4">
                  <span className="eve-label">{p.label} · {sec}</span>
                  <p className="mt-2 text-xs leading-relaxed text-[#aaaab5]">{p.text}</p>
                </div>
              )))}
            </div>
          </div>
        </div>
      )}

      {view === 'advanced · face' && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <input value={importPath} onChange={(e) => setImportPath(e.target.value)}
              className="eve-input h-10 flex-1 min-w-[240px]" placeholder="C:\path\to\face.png" />
            <button onClick={onImport} className="eve-button border border-[#353541]">import</button>
            <label className="eve-button border border-[#353541] cursor-pointer">upload
              <input type="file" accept="image/*" hidden onChange={onUploadRef} /></label>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {refs.map((r) => (
              <div key={r.name} className={`eve-card overflow-hidden ${bio?.reference === r.name ? 'border-[#4ea1ff]' : ''}`}>
                <div className="relative">
                  <img src={`/api/refs/${r.name}/file?t=${stamp}`} className="aspect-[4/5] w-full object-cover" alt={r.name} />
                  {bio?.reference === r.name && <span className="absolute left-2 top-2 rounded bg-[#4ea1ff] px-2 py-1 text-[9px] font-bold text-black">★ BIO</span>}
                  {!r.usable && <span className="absolute right-2 top-2 rounded bg-[#40201f] px-2 py-1 text-[9px] text-[#f17b72]">no face</span>}
                </div>
                <div className="p-3">
                  <p className="truncate font-mono text-[10px]">{r.name}</p>
                  <p className="mt-1 text-[10px] text-[#777785]">{r.face_px ?? '—'}px · yaw {r.yaw > 0 ? '+' : ''}{r.yaw ?? 0}°</p>
                  <div className="mt-3 flex items-center gap-3 text-[10px]">
                    <button disabled={!r.usable || bio?.reference === r.name} onClick={() => onSetBio(r.name)}
                      className="text-[#65aff9] disabled:opacity-40"><Star className="inline h-3 w-3" /> {bio?.reference === r.name ? 'is BIO' : 'set BIO'}</button>
                    <button onClick={() => onToGallery(r)} className="text-[#8a8a99] hover:text-[#e6e6ea]">→ gallery</button>
                    <button onClick={() => onDeleteRef(r.name)} className="ml-auto text-[#6c6c79] hover:text-[#e2564a]"><Trash2 className="h-3 w-3" /></button>
                  </div>
                </div>
              </div>
            ))}
            {!refs.length && <p className="text-xs text-[#767684]">No identity references yet. Import or upload one.</p>}
          </div>
        </>
      )}

      {view === 'advanced · body' && (
        <>
          <p className="help">
            Her figure comes from this <b>body reference</b> image (@image2). To set an exact shape, generate a
            new one: your <b>body text</b> drives the proportions, and you can add an optional <b>body-shape
            reference image</b> below to pin the exact hourglass/curve. Identity always stays with the face —
            only the figure comes from the shape ref. Review, then lock it in and every shot inherits it.
          </p>
          {/* saved body-type library — select one to make it the active figure */}
          <div className="mb-5">
            <p className="eve-label mb-2">body types — click to make active</p>
            {bodies.length === 0
              ? <p className="text-xs text-[#767684]">No saved body types yet. Generate one below and save it with a name — then it's a selectable figure here.</p>
              : <div className="wardrobe-strip">
                  {bodies.map((b) => (
                    <div key={b.id} className={`wcard ${b.active ? 'on' : ''}`} title={b.build}
                      style={{ height: 'auto' }}>
                      <img alt={b.id} src={`/api/bodies/${b.file}/file`} onClick={() => onSelectBody(b.id)} style={{ cursor: 'pointer', height: 96 }} />
                      <span>{b.active ? `★ ${b.id}` : b.id}</span>
                      <button onClick={() => onDeleteBody(b.id)} title="delete"
                        style={{ position: 'absolute', top: 2, right: 2, background: 'rgba(0,0,0,.6)', border: 'none', color: '#e2564a', fontSize: 11, cursor: 'pointer', borderRadius: 4, padding: '0 4px' }}>✕</button>
                    </div>
                  ))}
                </div>}
          </div>
          <div className="grid gap-5 md:grid-cols-[280px_1fr]">
            <div className="eve-card overflow-hidden">
              {bio?.body_reference
                ? <img src={`/api/refs/${bio.body_reference}/file?t=${stamp}`} className="aspect-[3/4] w-full object-cover" alt="body reference" />
                : <div className="p-6 text-xs text-[#767684]">no body reference set</div>}
              <div className="p-3">
                <p className="eve-label text-[#4ea1ff]">active body reference</p>
                <p className="mt-1 font-mono text-[10px] text-[#777785]">{bodies.find((b) => b.active)?.id || bio?.body_reference || '—'}</p>
              </div>
            </div>
            <div>
              {/* optional body-SHAPE reference — pins the exact figure; identity still comes from the face */}
              <div className="mb-3 flex items-center gap-3">
                {shapeRef
                  ? <div className="relative">
                      <img src={`/api/refs/${shapeRef}/file?t=${stamp}`} className="h-20 w-16 rounded-md border border-[#315d88] object-cover" alt="shape ref" />
                      <button onClick={() => setShapeRef(null)} title="remove shape reference"
                        className="absolute -right-2 -top-2 rounded-full bg-[#2a2a34] p-0.5 text-[#e2564a]"><X className="h-3 w-3" /></button>
                    </div>
                  : <label className="flex h-20 w-16 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-[#3a3a46] bg-[#0e0e12] text-center text-[9px] text-[#8a8a99] transition hover:border-[#4ea1ff] hover:text-[#cfe0f5]">
                      <ImagePlus className="h-4 w-4" />
                      shape ref
                      <input type="file" accept="image/*" hidden onChange={uploadShape} />
                    </label>}
                <p className="flex-1 text-[11px] text-[#767684]">
                  <b className="text-[#8fb6dd]">Optional body-shape reference.</b> Point at a figure to match the
                  exact hourglass/curve — only the <b>proportions</b> are taken from it; her face &amp; identity stay
                  locked. Use a generated or non-identifiable figure, <b>not a photo of a real person</b>.
                </p>
              </div>
              {/* Explicit figure text — this drives the body image (a clothed solo figure on
                  the permissive model), so strong curve wording is fine HERE and renders far
                  curvier than the tasteful bio text. Blank = use her bio build. */}
              <label className="mb-1 block eve-label text-[#8a8a99]">figure for this body <span className="text-[#5f5f6c]">— optional, be explicit for curvy</span></label>
              <textarea value={figure} onChange={(e) => setFigure(e.target.value)} rows={2}
                placeholder="e.g. dramatically curvy voluptuous hourglass — a very full heavy bust, cinched narrow waist, wide full hips; full-figured, not slim"
                className="mb-2 w-full resize-none rounded-md border border-[#2a2a34] bg-[#0e0e12] px-3 py-2 text-xs leading-relaxed text-[#e6e6ea] outline-none focus:border-[#4ea1ff]" />
              <button onClick={() => onCreateBody(shapeRef, figure.trim())} disabled={!!bodyCreating}
                className="eve-button bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff]">
                {bodyCreating ? 'generating…' : `generate body reference${shapeRef ? ' (+ shape ref)' : ''}`}
              </button>
              {bodyCreating && (
                <div className="mt-3 flex items-center gap-3 rounded-lg border border-[#315d88] bg-[#101b27] p-4">
                  <LoaderCircle className="h-5 w-5 animate-spin text-[#4ea1ff]" />
                  <span className="text-sm text-[#8fb6dd]">{bodyCreating} · ~1–2 min</span>
                </div>
              )}
              {bodyPreview && (
                <div className="mt-4 rounded-lg border border-[#315d88] bg-[#101b27] p-3">
                  <span className="eve-label text-[#72b8ff]">preview — save as body reference or discard</span>
                  {bodyPreview.moderation_fallback && <span className="ml-2 eve-chip text-[#edb755]">scene-model</span>}
                  <img src={`/api/images/${bodyPreview.file}`} className="mt-2 w-full rounded-md border border-[#24242e]" alt="body preview" />
                  <div className="mt-3 flex gap-2">
                    <button onClick={onSaveBody} className="eve-button bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff]">save as body type</button>
                    <button onClick={onDiscardBody} className="eve-button border border-[#353541]">discard</button>
                  </div>
                </div>
              )}
              <p className="mt-4 text-xs text-[#767684]">
                Uses your body parts — edit <b>bust / waist / hips</b> under <b>advanced · parts</b> (body)
                first, then generate. Size wording now passes moderation; if gpt-image-2 refuses, it falls
                back to the scene model.
              </p>
            </div>
          </div>
        </>
      )}

      {view === 'advanced · parts' && (
        <div className="space-y-4">
          {sections.map((sec) => (
            <div key={sec}>
              <p className="eve-label mb-2">{sec}</p>
              <div className="space-y-2">
                {parts.filter((p) => p.section === sec).map((p) => (
                  <div key={p.id} className={`eve-panel flex gap-4 ${p.enabled ? '' : 'opacity-50'}`}>
                    <input type="checkbox" checked={p.enabled} className="mt-1"
                      onChange={(e) => savePart(p.id, { enabled: e.target.checked })} />
                    <div className="w-full">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{p.label}</span>
                        {p.identity && <span className="eve-chip">identity</span>}
                        {p.critical && <span className="eve-chip text-[#edb755]">load-bearing</span>}
                        <code className="ml-auto font-mono text-[10px] text-[#565663]">{p.id}</code>
                      </div>
                      <textarea defaultValue={p.text} onBlur={(e) => savePart(p.id, { text: e.target.value })}
                        rows={p.text.length > 120 ? 4 : 2}
                        className="mt-3 w-full resize-none rounded border border-[#292933] bg-[#0e0e12] p-3 font-mono text-xs text-[#aaaab5] outline-none focus:border-[#4ea1ff]" />
                      {p.note && <p className="mt-2 text-[11px] text-[#6c6c79]">{p.note}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          <button onClick={onResetParts} className="eve-button border border-[#353541]">reset to defaults</button>
        </div>
      )}
    </main>
  )
}
