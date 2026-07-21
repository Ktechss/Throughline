import { useState } from 'react'
import { Film, Wand2, LoaderCircle, MessageSquare, Sparkles, Check } from 'lucide-react'

const MODEL_LABEL = {
  'seedance': 'Seedance 1.0 Pro',
  'kling': 'Kling 2.1',
  'happy-horse': 'happy-horse',
}
const MODEL_NOTE = {
  'seedance': 'cinematic scene motion · permissive',
  'kling': 'gentle · most identity-safe',
  'happy-horse': 'face-safe · native audio + lip-sync (talking)',
}

// Animate a gate-approved still on fal. happy-horse adds a full configurator:
// dialogue (auto lip-sync), resolution, duration, seed, safety checker.
export default function VideoStudio({ runs, cameraMoves = [], models = [], videos = [], onAnimate, onDirect, busy, stamp = 0 }) {
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

  const direct = async () => {
    if (!scenario.trim() || directing) return
    setDirecting(true)
    try {
      const plan = await onDirect(scenario.trim())
      if (plan.model) setModel(plan.model)
      setDialogue(plan.dialogue || '')
      setExtra(plan.scene || '')
      if (plan.camera_move) setMove(plan.camera_move)
      if (plan.duration) setDuration(plan.duration)
      if (plan.resolution) setResolution(plan.resolution)
      setNote(plan.note || '')
    } catch { /* error surfaced by App */ } finally { setDirecting(false) }
  }

  // pickable = the gate kept it OR you approved it by hand (the mark override)
  const stills = runs.filter((r) => r.file && r.meta && 'brief' in r.meta
    && (r.verdict?.status === 'kept' || r.mark === 'approve'))
  const selected = stills.find((r) => r.id === still)
  const isHH = model === 'happy-horse'

  const moveHint = {
    'static': 'locked camera · safest identity',
    'dolly-in': 'push in · flattering, identity-safe',
    'orbit': 'circles her · shows outfit in 3D (turns her head)',
    'crash-zoom': 'fast push · dramatic, best as a beat',
    'pull-back': 'reveals the full look',
  }

  const go = () => {
    if (!selected || busy) return
    onAnimate({
      run_id: selected.id, file: selected.file, camera_move: move, model,
      extra: extra.trim(), dialogue: isHH ? dialogue.trim() : '',
      resolution, duration: Number(duration), enable_safety_checker: safety,
      keep_audio: isHH ? keepAudio : true,
      seed: seed.trim() === '' ? null : Number(seed),
    })
  }

  const Field = ({ label, children }) => (
    <label className="block">
      <span className="eve-label">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-7">
      <div className="mb-5">
        <p className="eve-label flex items-center gap-2"><Film className="h-3.5 w-3.5 text-[#4ea1ff]" /> video studio · fal</p>
        <h1 className="mt-2 text-2xl font-semibold">Animate a still</h1>
        <p className="mt-2 max-w-2xl text-sm text-[#8a8a99]">Pick a gate-approved shot, configure the model, generate on fal. <b className="text-[#e6e6ea]">happy-horse</b> accepts her face and lip-syncs dialogue — a full talking clip in one call.</p>
      </div>

      {/* STEP 1 — pick a still */}
      <section className="eve-panel mb-5">
        <p className="eve-label mb-3">1 · pick a still <span className="text-[#666674]">(gate-approved or manually approved)</span></p>
        {stills.length === 0
          ? <p className="text-xs text-[#767684]">No approved shots yet. Generate some in <b className="text-[#e6e6ea]">shoot</b>, or approve some in <b className="text-[#e6e6ea]">review</b>.</p>
          : <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8">
              {stills.slice(0, 30).map((r) => (
                <button key={r.id} onClick={() => setStill(r.id)}
                  className={`eve-card relative overflow-hidden transition ${still === r.id ? 'ring-2 ring-[#4ea1ff]' : ''}`}>
                  <img src={`/api/images/${r.file}/thumb`} loading="lazy" className="aspect-[3/4] w-full object-cover" alt="" />
                  <span className="absolute right-1 top-1" title={r.mark === 'approve' ? 'you approved this' : 'gate-approved'}>
                    {r.mark === 'approve'
                      ? <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[#33c07f] text-black"><Check className="h-2.5 w-2.5" /></span>
                      : <span className="h-2 w-2 rounded-full bg-[#4ea1ff] ring-2 ring-black/40" />}
                  </span>
                </button>
              ))}
            </div>}
        <p className="mt-2 text-[10px] text-[#666674]"><span className="text-[#33c07f]">✓</span> you approved · <span className="text-[#4ea1ff]">•</span> gate-approved</p>
      </section>

      {/* STEP 2 — AI director */}
      <section className="eve-panel mb-5">
        <div className="mb-3 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[#4ea1ff]" />
          <p className="eve-label text-[#67aff8]">2 · describe the scene — the AI directs it</p>
        </div>
        <textarea value={scenario} onChange={(e) => setScenario(e.target.value)} rows={2}
          className="eve-input w-full resize-y"
          placeholder="e.g. she's at a rooftop party introducing herself for her first post · or: styling a bride, talking through the look" />
        <button onClick={direct} disabled={!scenario.trim() || directing}
          className="eve-button mt-3 border border-[#284d72] bg-[#101923] text-[#8fb6dd] disabled:opacity-40">
          {directing ? <><LoaderCircle className="h-4 w-4 animate-spin" /> directing…</> : <><Sparkles className="h-3.5 w-3.5" /> direct this scene</>}
        </button>
        <span className="ml-3 text-[11px] text-[#8a8a99]">fills every setting below — you can tweak it, then generate</span>
        {note && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-[#284d72] bg-[#101923] p-3">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#4ea1ff]" />
            <p className="text-xs text-[#8fb6dd]"><b className="text-[#c7dcf0]">Director's picks:</b> {note} <span className="text-[#6f8299]">— tuned for this scene; change anything below only if you want to.</span></p>
          </div>
        )}
      </section>

      {/* STEP 3 — model + configurator */}
      <section className="eve-panel mb-5">
        <p className="eve-label mb-3">3 · model &amp; controls</p>
        <div className="flex flex-wrap gap-2">
          {models.map((md) => (
            <button key={md} onClick={() => setModel(md)} title={MODEL_NOTE[md]}
              className={`rounded-md border px-3 py-1.5 text-xs transition ${model === md
                ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>
              {MODEL_LABEL[md] || md}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-[#8a8a99]">{MODEL_NOTE[model]}</p>

        {/* camera move (prompt guidance for all models) */}
        <p className="eve-label mb-2 mt-5">camera move</p>
        <div className="flex flex-wrap gap-2">
          {cameraMoves.map((m) => (
            <button key={m} onClick={() => setMove(m)} title={moveHint[m]}
              className={`rounded-full border px-3 py-1.5 text-xs transition ${move === m
                ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6] hover:border-[#3a3a46]'}`}>{m}</button>
          ))}
        </div>

        {/* happy-horse configurator */}
        {isHH && (
          <div className="mt-5 space-y-4 rounded-lg border border-[#284d72] bg-[#0e1620] p-4">
            <p className="eve-label flex items-center gap-2 text-[#67aff8]"><MessageSquare className="h-3.5 w-3.5" /> happy-horse configurator</p>
            <Field label="dialogue — what she says (blank = silent)">
              <textarea value={dialogue} onChange={(e) => setDialogue(e.target.value)} rows={2}
                className="eve-input w-full resize-y" placeholder="e.g. Okay hi — this is my first post and I don't know what to say." />
            </Field>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Field label="resolution">
                <div className="flex gap-1">
                  {['720p', '1080p'].map((r) => (
                    <button key={r} onClick={() => setResolution(r)}
                      className={`flex-1 rounded-md border px-2 py-1 text-xs ${resolution === r ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6]'}`}>{r}</button>
                  ))}
                </div>
              </Field>
              <Field label={`duration · ${duration}s`}>
                <input type="range" min={3} max={15} value={duration} onChange={(e) => setDuration(+e.target.value)} className="w-full accent-[#4ea1ff]" />
              </Field>
              <Field label="seed (blank = random)">
                <input value={seed} onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ''))} className="eve-input h-9 w-full" placeholder="random" />
              </Field>
              <Field label="safety checker">
                <button onClick={() => setSafety((s) => !s)}
                  className={`h-9 w-full rounded-md border text-xs ${safety ? 'border-[#33c07f] bg-[#123020] text-[#62d99d]' : 'border-[#5d2926] bg-[#211313] text-[#f18b84]'}`}>
                  {safety ? 'on (moderated)' : 'off'}
                </button>
              </Field>
              <Field label="audio">
                <button onClick={() => setKeepAudio((a) => !a)}
                  title="happy-horse always generates audio; off strips it to a silent clip"
                  className={`h-9 w-full rounded-md border text-xs ${keepAudio ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]' : 'border-[#2a2a34] text-[#a9a9b6]'}`}>
                  {keepAudio ? 'keep audio' : 'silent'}
                </button>
              </Field>
            </div>
            {!dialogue.trim() && keepAudio && <p className="text-[11px] text-[#d99a2b]">No dialogue — happy-horse will add its own ambient/music. Set audio to "silent" to drop it.</p>}
            {!safety && <p className="text-[11px] text-[#d99a2b]">Safety checker off disables NSFW filtering — keep it on for normal content.</p>}
          </div>
        )}

        <div className="mt-4">
          <input value={extra} onChange={(e) => setExtra(e.target.value)}
            className="eve-input h-9 w-full" placeholder="optional: extra motion / scene words (e.g. 'lights flashing, she laughs')" />
        </div>

        <button onClick={go} disabled={!selected || !!busy}
          className="eve-button mt-4 bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff] disabled:opacity-40">
          {busy ? <><LoaderCircle className="h-4 w-4 animate-spin" /> {busy}</> : <><Wand2 /> generate video</>}
        </button>
        {!selected && <span className="ml-3 text-[11px] text-[#8a8a99]">pick a still above first</span>}
        <p className="mt-3 font-mono text-[10px] text-[#666674]">on fal · frames auto-gated for identity drift</p>
      </section>

      {/* clips */}
      <section>
        <p className="eve-label mb-3">your clips <span className="text-[#666674]">({videos.length})</span></p>
        {videos.length === 0
          ? <p className="text-xs text-[#767684]">No clips yet — animate a still above.</p>
          : <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {videos.map((v) => (
                <article key={v.id} className="eve-card overflow-hidden">
                  <video src={`/api/videos/${v.file}?t=${stamp}`} controls loop playsInline
                    className="aspect-[9/16] w-full bg-black object-cover" />
                  <div className="p-2">
                    <div className="flex items-center justify-between font-mono text-[10px] text-[#8a8a99]">
                      <span className="eve-chip">{v.dialogue ? 'talking' : v.camera_move}</span>
                      <span>{MODEL_LABEL[v.model] || v.model}</span>
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
