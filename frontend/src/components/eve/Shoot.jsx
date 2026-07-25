import { useRef, useState } from 'react'
import { LockKeyhole, ImagePlus, LoaderCircle, Sparkles } from 'lucide-react'
import PoseIcon from './PoseIcon'
import RefStrip from './RefStrip'
import WardrobePanel from './WardrobePanel'
import PromptControls from './PromptControls'
import GenerationCard from './GenerationCard'

// Group the text-pose presets by posture so the picker reads at a glance.
// Portrait/headshot framings come first — they're the highest-scoring shots.
const PORTRAIT = new Set(['headshot', 'portrait', 'close-up', 'beauty',
  'three-quarter', 'profile', 'laughing', 'looking-away', 'chin-hand'])
const POSE_CAT = (id) =>
  PORTRAIT.has(id) ? 'portrait'
    : id.startsWith('seated') ? 'sitting'
      : (id.startsWith('reclining') || id.startsWith('lying') || id.startsWith('lounging')) ? 'lying down'
        : (id.startsWith('kneeling') || id.startsWith('crouching') || id === 'squatting') ? 'low'
          : 'standing'
const POSE_ORDER = ['portrait', 'standing', 'sitting', 'low', 'lying down']

export default function Shoot({
  bio, gens, onOpen, goBio,
  brief, setBrief, aiPrompt, setAiPrompt, aiBusy, onAiPrompt, onGenerate,
  outfit, setOutfit, poseRef, setPoseRef, wardrobe, poseRefs,
  poseId, setPoseId, poseLibrary, resolution, setResolution, faceAcc, setFaceAcc,
  outfitText, setOutfitText, describing, onDescribe, creating, onCreateOutfit,
  outfitPreview, onSaveOutfit, onDiscardOutfit, onOpenDesigner,
  saveCategory, setSaveCategory,
  onUploadOutfit, onUploadPose, onDeleteWardrobe, stamp,
}) {
  const canGenerate = !!bio?.reference && (!!brief.trim() || !!outfit || !!poseRef)
  const [poseTab, setPoseTab] = useState('portrait')
  const poseCats = POSE_ORDER.filter((cat) => (poseLibrary || []).some((p) => p.id && POSE_CAT(p.id) === cat))
  const activePoseTab = poseCats.includes(poseTab) ? poseTab : (poseCats[0] || 'standing')
  const gensRef = useRef(null)
  const handleGenerate = () => {
    onGenerate()
    // jump to the queue so the new card is visible (it lives below the fold)
    setTimeout(() => gensRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }
  // Categories present in the wardrobe (+ any just-typed new one), for the save chips.
  const wardrobeCats = [...new Set((wardrobe || []).map((w) => w.category).filter(Boolean))]
  const saveCats = [...new Set([...wardrobeCats, ...(saveCategory && !wardrobeCats.includes(saveCategory) ? [saveCategory] : [])])]
  // Preview the auto name <Category><next#> — mirrors the backend numbering.
  const nextName = (cat) => {
    const c = (cat || '').replace(/[^a-zA-Z0-9]/g, '')
    if (!c) return ''
    const canon = c[0].toUpperCase() + c.slice(1)
    let mx = 0
    for (const w of (wardrobe || [])) {
      const m = (w.id || '').match(new RegExp(`^${canon}(\\d+)$`, 'i'))
      if (m) mx = Math.max(mx, +m[1])
      else if ((w.id || '').toLowerCase() === canon.toLowerCase()) mx = Math.max(mx, 1)
    }
    return `${canon}${mx + 1}`
  }
  return (
    <main className="mx-auto max-w-[1340px] space-y-6 px-5 py-7">
      <button onClick={goBio} className="flex w-full items-center gap-3 rounded-lg border border-[#284d72] bg-[#101923] p-3 text-left">
        {bio?.reference
          ? <img src={`/api/refs/${bio.reference}/thumb?t=${stamp}`} loading="lazy" className="h-11 w-11 rounded object-cover" alt="bio" />
          : <div className="flex h-11 w-11 items-center justify-center rounded bg-[#1b2b3d] text-[#d99a2b]">!</div>}
        <div>
          <span className="eve-label text-[#67aff8]">{bio?.reference ? 'BIO · identity locked' : 'BIO · not set'}</span>
          <p className="mt-1 text-xs text-[#aaaab6]">
            {bio?.reference
              ? `${bio.reference} · ${bio.reference_face?.face_px}px · ${bio.gallery?.entries?.length || 0} angles · attached to every shot`
              : 'set an identity reference under bio › advanced · face'}
          </p>
        </div>
        <LockKeyhole className="ml-auto h-4 w-4 text-[#4ea1ff]" />
      </button>

      <div className="grid gap-6 lg:grid-cols-[1fr_460px]">
      <section className="eve-panel space-y-5">
        <PromptControls brief={brief} setBrief={setBrief} prompt={aiPrompt} setPrompt={setAiPrompt}
          onGenerate={handleGenerate} onAiPrompt={onAiPrompt} aiBusy={aiBusy}
          selected={{ outfit, pose: poseRef }} canGenerate={canGenerate} />

        <div className="flex items-center gap-3">
          <span className="eve-label">resolution</span>
          <div className="flex gap-1">
            {[['1K', '~1080p · light'], ['2K', '~1440p'], ['4K', 'max · heavy']].map(([r, hint]) => (
              <button key={r} onClick={() => setResolution(r)} title={hint}
                className={`rounded-md border px-3 py-1 text-xs transition ${resolution === r
                  ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
                  : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>{r}</button>
            ))}
          </div>
          <span className="font-mono text-[10px] text-[#666674]">
            {resolution === '4K' ? '~20 MB/image' : resolution === '2K' ? '~5 MB/image' : '~1.5 MB/image · smaller face, may abstain on full-body'}
          </span>
        </div>

        {/* Face-worn accessories (sunglasses, hats) from the selected outfit. Off
            keeps her face clear → best identity score; on renders the full look. */}
        <div className="flex items-center gap-3">
          <span className="eve-label">face accessories</span>
          <button onClick={() => setFaceAcc(!faceAcc)} role="switch" aria-checked={faceAcc}
            className={`relative h-5 w-9 rounded-full border transition ${faceAcc
              ? 'border-[#4ea1ff] bg-[#123049]' : 'border-[#2a2a34] bg-[#0e0e12]'}`}>
            <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${faceAcc
              ? 'left-4 bg-[#4ea1ff]' : 'left-0.5 bg-[#565663]'}`} />
          </button>
          <span className="font-mono text-[10px] text-[#666674]">
            {faceAcc
              ? 'sunglasses / hats from the outfit render (may lower identity score)'
              : 'face kept clear — no sunglasses/hats · best for identity'}
          </span>
        </div>
        <div>
          <p className="eve-label mb-2">outfit builder</p>
          <div className="flex flex-wrap gap-2">
            <input value={outfitText} onChange={(e) => setOutfitText(e.target.value)}
              className="eve-input h-10 flex-1 min-w-[220px]"
              placeholder="describe an outfit — 'red satin slip dress, strappy heels'" />
            <button onClick={onOpenDesigner} className="eve-button shrink-0 border border-[#315d88] bg-[#101b27] text-[#8fb6dd] hover:border-[#4ea1ff]">
              <Sparkles /> outfit designer
            </button>
            <button onClick={onCreateOutfit} disabled={!!creating || !outfitText.trim()}
              className="eve-button shrink-0 border border-[#353541]">{creating ? 'creating…' : 'create outfit'}</button>
          </div>

          {creating && !outfitPreview && (
            <div className="mt-3 flex items-center gap-3 rounded-lg border border-[#315d88] bg-[#101b27] p-4">
              <LoaderCircle className="h-5 w-5 shrink-0 animate-spin text-[#4ea1ff]" />
              <div>
                <span className="eve-label text-[#72b8ff]">creating outfit turnaround…</span>
                <p className="mt-1 text-xs text-[#8fb6dd]">{creating} · ~1–2 min · the preview appears here to save or discard</p>
              </div>
            </div>
          )}

          {outfitPreview && (
            <div className="mt-3 rounded-lg border border-[#315d88] bg-[#101b27] p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="eve-label text-[#72b8ff]">outfit preview — save it or discard</span>
                {outfitPreview.moderation_fallback && <span className="eve-chip text-[#edb755]">scene-model</span>}
              </div>
              <img src={`/api/images/${outfitPreview.file}`} className="w-full rounded-md border border-[#24242e]" alt="outfit preview" />
              <p className="mt-3 eve-label text-[#8a8a99]">save to category</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {saveCats.map((c) => (
                  <button key={c} onClick={() => setSaveCategory(c)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${saveCategory === c
                      ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
                      : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>{c}</button>
                ))}
                <button onClick={() => { const n = window.prompt('New category name:'); if (n && n.trim()) setSaveCategory(n.trim()) }}
                  className="rounded-full border border-dashed border-[#3a3a46] px-3 py-1 text-xs text-[#8a8a99] transition hover:border-[#4ea1ff] hover:text-[#cfe0f5]">＋ new category</button>
              </div>
              {saveCategory && <p className="mt-1.5 text-[10px] text-[#5f6b7a]">will save as <b className="text-[#9fd0ff]">{nextName(saveCategory)}</b></p>}
              <div className="mt-2 flex gap-2">
                <button onClick={onSaveOutfit} disabled={!saveCategory}
                  className="eve-button bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff] disabled:opacity-40">save to wardrobe</button>
                <button onClick={onDiscardOutfit} className="eve-button border border-[#353541]">discard</button>
              </div>
            </div>
          )}
        </div>

        {/* Text pose presets — category TABS + visual pose cards. */}
        <div>
          <div className="mb-2 flex items-center gap-2">
            <p className="eve-label">pose</p>
            <span className="font-mono text-[9px] text-[#666674]">native · text-driven</span>
            {poseId && <button onClick={() => setPoseId('')} className="ml-auto text-[10px] text-[#8a8a99] hover:text-[#e6e6ea]">clear</button>}
          </div>

          {/* category tabs */}
          <div className="flex flex-wrap gap-1 border-b border-[#24242e]">
            {poseCats.map((cat) => (
              <button key={cat} onClick={() => setPoseTab(cat)}
                className={`-mb-px border-b-2 px-3 py-1.5 text-xs capitalize transition ${activePoseTab === cat
                  ? 'border-[#4ea1ff] text-[#e6e6ea]'
                  : 'border-transparent text-[#70707d] hover:text-[#b8b8c3]'}`}>{cat}</button>
            ))}
          </div>

          {/* pose cards for the active tab */}
          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {(poseLibrary || []).filter((p) => p.id && POSE_CAT(p.id) === activePoseTab).map((p) => {
              const on = poseId === p.id
              return (
                <button key={p.id} title={p.text} onClick={() => setPoseId(on ? '' : p.id)}
                  className={`flex flex-col items-center gap-1 rounded-lg border p-2 text-center transition ${on
                    ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
                    : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a4a5e] hover:text-[#e6e6ea]'}`}>
                  <PoseIcon id={p.id} className="h-8 w-8" />
                  <span className="w-full truncate text-[10px] leading-tight">{p.id}</span>
                </button>
              )
            })}
          </div>
          {poseId && <p className="mt-2 text-[11px] text-[#8fb6dd]">{(poseLibrary.find((p) => p.id === poseId) || {}).text}</p>}
        </div>

        <RefStrip title="pose reference (optional override)" tag="@image3" items={poseRefs} selected={poseRef} onSelect={setPoseRef} onUpload={onUploadPose} urlBase="/api/pose-refs" />
      </section>

      <WardrobePanel items={wardrobe} selected={outfit} onSelect={setOutfit}
        onDelete={onDeleteWardrobe} onUpload={onUploadOutfit} stamp={stamp} />
      </div>

      <div ref={gensRef} className="scroll-mt-20">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <p className="eve-label">generations</p>
            <h2 className="mt-1 text-lg">Parallel queue</h2>
          </div>
          <span className="font-mono text-[10px] text-[#666674]">{gens.length} frames</span>
        </div>
        {gens.length === 0
          ? <p className="text-xs text-[#767684]">Hit <b className="text-[#e6e6ea]">generate</b> — a card appears here and fills in when it’s done. Fire as many as you like; they run in parallel. Click any finished image for its origin.</p>
          : <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {gens.map((v) => <GenerationCard key={v.id} v={v} onOpen={onOpen} />)}
            </div>}
      </div>
    </main>
  )
}
