import { useState } from 'react'
import { Film, Wand2, LoaderCircle, MessageSquare, Sparkles, Check, Clapperboard } from 'lucide-react'

const MODEL_LABEL = { 'seedance': 'Seedance 1.0 Pro', 'kling': 'Kling 2.1', 'happy-horse': 'happy-horse' }
const MODEL_NOTE = {
  'seedance': 'cinematic scene motion · permissive',
  'kling': 'gentle · most identity-safe',
  'happy-horse': 'face-safe · native audio + lip-sync (talking)',
}

export default function VideoStudio({ runs, cameraMoves = [], models = [], videos = [], wardrobe = [],
  onAnimate, onDirect, onGenerateStill, onMakeVideo, busy, makeBusy, stamp = 0 }) {
  const [mode, setMode] = useState('animate')   // 'animate' | 'make'

  // --- animate-still state ---
  const [still, setStill] = useState(null)
  const [move, setMove] = useState('dolly-in')
  const [model, setModel] = useState('happy-horse')
  const [extra, setExtra] = useState('')
  const [dialogue, setDialogue] = useState('')
  const [resolution, setResolution] = useState('1080p')
  const [duration, setDuration] = useState(5)
  const [seed, setSeed] = useState('')
  const [safety, setSafety] = useState(true)
  const [keepAudio, setKeepAudio] = useState(true)
  const [scenario, setScenario] = useState('')
  const [directing, setDirecting] = useState(false)
  const [note, setNote] = useState('')
  const [imageBrief, setImageBrief] = useState('')
  const [wardrobePick, setWardrobePick] = useState('')
  const [stillBusy, setStillBusy] = useState(false)

  // --- make-video state ---
  const [mkScenario, setMkScenario] = useState('')
  const [mkWardrobe, setMkWardrobe] = useState('')   // '' = director picks
  const [mkDuration, setMkDuration] = useState(15)

  const stills = runs.filter((r) => r.file && r.meta && 'brief' in r.meta
    && (r.verdict?.status === 'kept' || r.mark === 'approve'))
  const selected = stills.find((r) => r.id === still)
  const isHH = model === 'happy-horse'

  const direct = async () => {
    if (!scenario.trim() || directing) return
    setDirecting(true)
    try {
      const p = await onDirect(scenario.trim())
      if (p.model) setModel(p.model)
      setDialogue(p.dialogue || ''); setExtra(p.scene || '')
      if (p.camera_move) setMove(p.camera_move)
      if (p.duration) setDuration(p.duration)
      if (p.resolution) setResolution(p.resolution)
      setNote(p.note || ''); setImageBrief(p.image_brief || ''); setWardrobePick(p.wardrobe || '')
    } catch { /* App surfaces */ } finally { setDirecting(false) }
  }
  const makeStill = async () => {
    if (!imageBrief.trim() || stillBusy) return
    setStillBusy(true)
    try { const run = await onGenerateStill({ brief: imageBrief.trim(), wardrobe: wardrobePick }); if (run?.id) setStill(run.id) }
    catch { /* App surfaces */ } finally { setStillBusy(false) }
  }
  const go = () => {
    if (!selected || busy) return
    onAnimate({
      run_id: selected.id, file: selected.file, camera_move: move, model,
      extra: extra.trim(), dialogue: isHH ? dialogue.trim() : '',
      resolution, duration: Number(duration), enable_safety_checker: safety,
      keep_audio: isHH ? keepAudio : true, seed: seed.trim() === '' ? null : Number(seed),
    })
  }
  const make = () => { if (mkScenario.trim() && !makeBusy) onMakeVideo({ scenario: mkScenario.trim(), wardrobe: mkWardrobe || null, duration: Number(mkDuration) }) }

  const Field = ({ label, children }) => (
    <label className="block"><span className="eve-label">{label}</span><div className="mt-1">{children}</div></label>
  )

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-7">
      <div className="mb-5">
        <p className="eve-label flex items-center gap-2"><Film className="h-3.5 w-3.5 text-[#4ea1ff]" /> video studio · fal</p>
        <h1 className="mt-2 text-2xl font-semibold">Video</h1>
      </div>

      {/* mode toggle */}
      <div className="mb-6 flex gap-2">
        <button onClick={() => setMode('animate')}
          className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition ${mode === 'animate' ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>
          <Wand2 className="h-4 w-4" /> Animate Still <span className="text-[10px] text-[#6f8299]">· one clip from a still</span>
        </button>
        <button onClick={() => setMode('make')}
          className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition ${mode === 'make' ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>
          <Clapperboard className="h-4 w-4" /> Make Video <span className="text-[10px] text-[#6f8299]">· multi-scene from a scenario</span>
        </button>
      </div>

      {/* ============ MAKE VIDEO ============ */}
      {mode === 'make' && (
        <section className="eve-panel mb-6">
          <div className="mb-3 flex items-center gap-2"><Clapperboard className="h-4 w-4 text-[#4ea1ff]" /><p className="eve-label text-[#67aff8]">describe the video — the director storyboards it into scenes</p></div>
          <textarea value={mkScenario} onChange={(e) => setMkScenario(e.target.value)} rows={3} className="eve-input w-full resize-y"
            placeholder="e.g. a day in Kiara's life styling a bride — getting ready, at the venue, the reveal, a happy sign-off" />
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="outfit">
              <select value={mkWardrobe} onChange={(e) => setMkWardrobe(e.target.value)} className="eve-input h-9 w-full">
                <option value="">auto — director picks</option>
                {wardrobe.map((w) => <option key={w.id} value={w.id}>{w.id}</option>)}
              </select>
            </Field>
            <Field label={`length · ~${mkDuration}s`}>
              <input type="range" min={6} max={30} step={1} value={mkDuration} onChange={(e) => setMkDuration(+e.target.value)} className="w-full accent-[#4ea1ff]" />
            </Field>
            <div className="flex items-end">
              <button onClick={make} disabled={!mkScenario.trim() || !!makeBusy}
                className="eve-button w-full bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff] disabled:opacity-40">
                {makeBusy ? <><LoaderCircle className="h-4 w-4 animate-spin" /> {makeBusy}</> : <><Clapperboard className="h-4 w-4" /> Make Video</>}
              </button>
            </div>
          </div>
          <p className="mt-3 font-mono text-[10px] text-[#666674]">storyboards N scenes → generates a wardrobe-matched still per scene (parallel) → animates each → stitches. ~a few minutes.</p>
        </section>
      )}

      {/* ============ ANIMATE STILL ============ */}
      {mode === 'animate' && <>
        <section className="eve-panel mb-5">
          <p className="eve-label mb-3">1 · pick a still <span className="text-[#666674]">(gate-approved or manually approved)</span></p>
          {stills.length === 0
            ? <p className="text-xs text-[#767684]">No approved shots yet. Generate some in <b className="text-[#e6e6ea]">shoot</b>, or approve some in <b className="text-[#e6e6ea]">review</b>.</p>
            : <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8">
                {stills.slice(0, 30).map((r) => (
                  <button key={r.id} onClick={() => setStill(r.id)} className={`eve-card relative overflow-hidden transition ${still === r.id ? 'ring-2 ring-[#4ea1ff]' : ''}`}>
                    <img src={`/api/images/${r.file}/thumb`} loading="lazy" className="aspect-[3/4] w-full object-cover" alt="" />
                    <span className="absolute right-1 top-1">{r.mark === 'approve'
                      ? <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[#33c07f] text-black"><Check className="h-2.5 w-2.5" /></span>
                      : <span className="block h-2 w-2 rounded-full bg-[#4ea1ff] ring-2 ring-black/40" />}</span>
                  </button>
                ))}
              </div>}
        </section>

        <section className="eve-panel mb-5">
          <div className="mb-3 flex items-center gap-2"><Sparkles className="h-4 w-4 text-[#4ea1ff]" /><p className="eve-label text-[#67aff8]">2 · describe the scene — the AI directs it</p></div>
          <textarea value={scenario} onChange={(e) => setScenario(e.target.value)} rows={2} className="eve-input w-full resize-y"
            placeholder="e.g. she introduces herself at a rooftop party, a little shy" />
          <button onClick={direct} disabled={!scenario.trim() || directing} className="eve-button mt-3 border border-[#284d72] bg-[#101923] text-[#8fb6dd] disabled:opacity-40">
            {directing ? <><LoaderCircle className="h-4 w-4 animate-spin" /> directing…</> : <><Sparkles className="h-3.5 w-3.5" /> direct this scene</>}
          </button>
          {note && <div className="mt-3 flex items-start gap-2 rounded-lg border border-[#284d72] bg-[#101923] p-3"><Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#4ea1ff]" /><p className="text-xs text-[#8fb6dd]"><b className="text-[#c7dcf0]">Director's picks:</b> {note}</p></div>}
          {imageBrief && (
            <div className="mt-3 rounded-lg border border-[#2a2a34] bg-[#0e0e12] p-3">
              <div className="flex items-center gap-2"><span className="eve-label">scene still to generate</span>{wardrobePick && <span className="eve-chip text-[#9fd0ff]">outfit: {wardrobePick}</span>}</div>
              <p className="mt-1.5 text-xs text-[#a9a9b6]">{imageBrief}</p>
              <button onClick={makeStill} disabled={stillBusy} className="eve-button mt-3 bg-[#173a2c] text-[#62d99d] disabled:opacity-40">
                {stillBusy ? <><LoaderCircle className="h-4 w-4 animate-spin" /> generating still…</> : <><Wand2 className="h-3.5 w-3.5" /> generate scene still {wardrobePick ? `(${wardrobePick})` : ''}</>}
              </button>
            </div>
          )}
        </section>

        <section className="eve-panel mb-5">
          <p className="eve-label mb-3">3 · model &amp; controls</p>
          <div className="flex flex-wrap gap-2">
            {models.map((md) => (
              <button key={md} onClick={() => setModel(md)} title={MODEL_NOTE[md]}
                className={`rounded-md border px-3 py-1.5 text-xs transition ${model === md ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6]'}`}>{MODEL_LABEL[md] || md}</button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-[#8a8a99]">{MODEL_NOTE[model]}</p>
          <p className="eve-label mb-2 mt-5">camera move</p>
          <div className="flex flex-wrap gap-2">
            {cameraMoves.map((m) => (
              <button key={m} onClick={() => setMove(m)} className={`rounded-full border px-3 py-1.5 text-xs transition ${move === m ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>{m}</button>
            ))}
          </div>
          {isHH && (
            <div className="mt-5 space-y-4 rounded-lg border border-[#284d72] bg-[#0e1620] p-4">
              <p className="eve-label flex items-center gap-2 text-[#67aff8]"><MessageSquare className="h-3.5 w-3.5" /> happy-horse configurator</p>
              <Field label="dialogue — what she says (blank = silent)"><textarea value={dialogue} onChange={(e) => setDialogue(e.target.value)} rows={2} className="eve-input w-full resize-y" placeholder="e.g. Okay hi — this is my first post…" /></Field>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                <Field label="resolution"><div className="flex gap-1">{['720p', '1080p'].map((r) => <button key={r} onClick={() => setResolution(r)} className={`flex-1 rounded-md border px-2 py-1 text-xs ${resolution === r ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6]'}`}>{r}</button>)}</div></Field>
                <Field label={`duration · ${duration}s`}><input type="range" min={3} max={15} value={duration} onChange={(e) => setDuration(+e.target.value)} className="w-full accent-[#4ea1ff]" /></Field>
                <Field label="seed"><input value={seed} onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ''))} className="eve-input h-9 w-full" placeholder="random" /></Field>
                <Field label="safety"><button onClick={() => setSafety((s) => !s)} className={`h-9 w-full rounded-md border text-xs ${safety ? 'border-[#33c07f] bg-[#123020] text-[#62d99d]' : 'border-[#5d2926] bg-[#211313] text-[#f18b84]'}`}>{safety ? 'on' : 'off'}</button></Field>
                <Field label="audio"><button onClick={() => setKeepAudio((a) => !a)} className={`h-9 w-full rounded-md border text-xs ${keepAudio ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6]'}`}>{keepAudio ? 'keep' : 'silent'}</button></Field>
              </div>
            </div>
          )}
          <div className="mt-4"><input value={extra} onChange={(e) => setExtra(e.target.value)} className="eve-input h-9 w-full" placeholder="optional: extra motion / scene words" /></div>
          <button onClick={go} disabled={!selected || !!busy} className="eve-button mt-4 bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff] disabled:opacity-40">
            {busy ? <><LoaderCircle className="h-4 w-4 animate-spin" /> {busy}</> : <><Wand2 /> generate video</>}
          </button>
          {!selected && <span className="ml-3 text-[11px] text-[#8a8a99]">pick a still above first</span>}
        </section>
      </>}

      {/* ============ CLIPS ============ */}
      <section>
        <p className="eve-label mb-3">your clips <span className="text-[#666674]">({videos.length})</span></p>
        {videos.length === 0
          ? <p className="text-xs text-[#767684]">No clips yet.</p>
          : <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {videos.map((v) => (
                <article key={v.id} className="eve-card overflow-hidden">
                  <video src={`/api/videos/${v.file}?t=${stamp}`} controls loop playsInline className="aspect-[9/16] w-full bg-black object-cover" />
                  <div className="p-2">
                    <div className="flex items-center justify-between font-mono text-[10px] text-[#8a8a99]">
                      <span className="eve-chip">{v.scenes ? `${v.scenes} scenes` : v.dialogue ? 'talking' : v.camera_move}</span>
                      <span>{v.duration ? `${v.duration}s` : ''} {MODEL_LABEL[v.model] || v.model}</span>
                    </div>
                    {v.dialogue && <p className="mt-1 truncate text-[10px] text-[#8fb6dd]">“{v.dialogue}”</p>}
                    <div className="mt-1.5 flex flex-wrap gap-1.5 font-mono text-[9px]">
                      {(v.frames || []).map((f, i) => {
                        const c = f.status === 'kept' ? '#33c07f' : f.status === 'rejected' ? '#e2564a' : '#d9a52b'
                        return <span key={i} style={{ color: c }}>{f.frame} {f.similarity ?? '—'} {f.status}</span>
                      })}
                    </div>
                  </div>
                </article>
              ))}
            </div>}
      </section>
    </main>
  )
}
