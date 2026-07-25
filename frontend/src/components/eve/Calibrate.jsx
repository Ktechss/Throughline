import { useState } from 'react'
import { LoaderCircle, ScanFace, Wand2, Check, ImagePlus, Star } from 'lucide-react'
import { api } from '@/lib/eve'

// The character-origin flow, staged:
//   1. SEED   — base image + BIO (who she is; drives all generation)
//   2. GENERATE & APPROVE — canonical faces from the seed; pick the on-model ones
//   3. LOCK   — approved faces seed the fingerprint + recalibrate the threshold
//
// The calibration faces (`cands`) and their generation/polling live in App, NOT
// here — so leaving this tab (or switching characters) never throws them away.
// This component only renders them and forwards actions up.
export default function Calibrate({ bio, gallery, stamp, onRefresh,
    cands = [], onGenerate, onToggle, onAddSelected, onSetIdentity,
    onUploadBase, onEditBio }) {
  const [count, setCount] = useState(6)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)

  const generate = async () => {
    if (!bio?.calib_seed && !bio?.reference) { setErr('Upload a base image first (Step 1).'); return }
    setBusy(true); setErr(null); setResult(null)
    try { await onGenerate(count) } finally { setBusy(false) }
  }
  const toggle = (jid) => onToggle(jid)
  const addSelected = () => onAddSelected()
  const setIdentity = (runId) => onSetIdentity(runId)
  const recalibrate = async () => {
    setErr(null)
    try { setResult(await api.send('/api/calibrate/recalibrate', 'POST', {})); await onRefresh() }
    catch (e) { setErr(String(e)) }
  }
  const reset = async () => {
    if (!window.confirm('Wipe the fingerprint to start a fresh calibration?')) return
    try { await api.send('/api/calibrate/reset', 'POST', {}); setResult(null); await onRefresh() }
    catch (e) { setErr(String(e)) }
  }

  const entries = gallery?.entries || []
  const nSel = cands.filter((c) => c.sel && c.id).length
  const step = (n, label) => <span className="eve-label"><span className="text-[#4ea1ff]">step {n}</span> · {label}</span>

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-7">
      <div className="mb-5">
        <p className="eve-label">calibration engine</p>
        <h1 className="mt-2 text-2xl font-semibold">Build the character</h1>
        <p className="mt-2 max-w-2xl text-sm text-[#8a8a99]">
          Start from a <b className="text-[#e6e6ea]">base image + BIO</b> — that's who she is, and it drives every
          generation. Approve the faces you like, and they seed the identity <b className="text-[#e6e6ea]">fingerprint</b>.
        </p>
      </div>

      {err && <div className="mb-4 rounded-md border border-[#5d2926] bg-[#211313] px-4 py-2 text-xs text-[#f18b84]">{err}</div>}

      {/* STEP 1 — seed */}
      <section className="eve-panel mb-5">
        <div className="mb-3">{step(1, 'identity seed — base image + BIO')}</div>
        <div className="flex flex-wrap items-center gap-4">
          {bio?.calib_seed
            ? <img src={`/api/refs/${bio.calib_seed}/file?t=${stamp}`} className="h-28 w-24 rounded-md border border-[#24242e] object-cover" alt="seed" />
            : <label className="flex h-28 w-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-[#3a3a46] bg-[#0e0e12] text-center text-[10px] text-[#8a8a99] transition hover:border-[#4ea1ff] hover:text-[#cfe0f5]">
                <ImagePlus className="h-5 w-5" />
                upload seed
                <input type="file" accept="image/*" hidden onChange={onUploadBase} />
              </label>}
          <div className="min-w-[240px] flex-1">
            <p className="text-sm font-medium">{bio?.calib_seed || 'no seed image set'}</p>
            <p className="mt-1 text-xs text-[#8a8a99]">
              This is the <b className="text-[#e6e6ea]">calibration seed</b> — every calibration face is generated from it.
              It is <b className="text-[#e6e6ea]">not</b> your default identity: uploading here never changes the BIO image.
              You set the identity later by promoting a generated face (<span className="text-[#ffd36e]">★ identity</span>).
            </p>
            {bio?.calib_seed_face && (
              <p className="mt-1 font-mono text-[10px] text-[#777785]">{bio.calib_seed_face.face_px}px · {bio.calib_seed_face.pose_class} · yaw {bio.calib_seed_face.yaw > 0 ? '+' : ''}{bio.calib_seed_face.yaw}°</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <label className="eve-button border border-[#353541] cursor-pointer">
                <ImagePlus /> upload base image
                <input type="file" accept="image/*" hidden onChange={onUploadBase} />
              </label>
              <button className="eve-button border border-[#353541]" onClick={onEditBio}>edit BIO text</button>
            </div>
          </div>
        </div>
      </section>

      {/* STEP 2 — generate & approve */}
      <section className="eve-panel mb-5">
        <div className="mb-3">{step(2, 'generate faces & pick the on-model ones')}</div>
        <div className="flex flex-wrap items-end gap-4">
          <label className="block">
            <span className="eve-label">how many faces</span>
            <input type="number" min={1} max={12} value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(12, +e.target.value || 1)))}
              className="mt-1 h-10 w-24 rounded-md border border-[#30303a] bg-[#0e0e12] px-3 text-sm text-[#e6e6ea] outline-none focus:border-[#4ea1ff]" />
          </label>
          <button onClick={generate} disabled={busy || (!bio?.calib_seed && !bio?.reference)}
            className="eve-button bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff]">
            <Wand2 /> {busy ? 'starting…' : 'generate faces'}
          </button>
          {nSel > 0 && (
            <button onClick={addSelected} disabled={busy} className="eve-button bg-[#173a2c] text-[#62d99d]">
              <Check /> add {nSel} to fingerprint
            </button>
          )}
          <span className="ml-auto font-mono text-[10px] text-[#767684]">canonical angles: front · ¾ · profile · tilts · expressions</span>
        </div>

        {cands.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {cands.map((c) => {
              if (c.running) return (
                <article key={c.jid} className="eve-card flex aspect-[3/4] flex-col items-center justify-center gap-3 bg-[#111117] p-4 text-center">
                  <LoaderCircle className="h-6 w-6 animate-spin text-[#4ea1ff]" />
                  <p className="text-xs text-[#8fb6dd]">{c.stage || 'generating…'}</p>
                  <span className="eve-chip">{c.angle}</span>
                </article>
              )
              if (c.error) return (
                <article key={c.jid} className="eve-card flex aspect-[3/4] flex-col items-center justify-center gap-2 border-[#5d2926] bg-[#211313] p-4 text-center">
                  <p className="text-sm text-[#f18b84]">failed</p><small className="text-[#9b6764]">{c.error}</small>
                  <span className="eve-chip">{c.angle}</span>
                </article>
              )
              const v = c.verdict || {}
              return (
                <div key={c.jid}
                  className={`eve-card relative overflow-hidden text-left transition ${c.sel ? 'ring-2 ring-[#62d99d]' : ''}`}>
                  <button onClick={() => toggle(c.jid)} className="block w-full">
                    <img src={`/api/images/${c.file}`} className="aspect-[3/4] w-full object-cover" alt={c.angle} />
                    {c.sel && <span className="absolute right-2 top-2 rounded-full bg-[#62d99d] p-1 text-black"><Check className="h-3 w-3" /></span>}
                  </button>
                  <button onClick={() => setIdentity(c.id)} title="Use as identity (@image1)"
                    className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 py-1 text-[10px] text-[#ffd36e] backdrop-blur hover:bg-black/80">
                    <Star className="h-3 w-3" /> identity
                  </button>
                  <div className="flex items-center justify-between p-2 font-mono text-[10px]">
                    <span className="eve-chip">{c.angle}</span>
                    <span className="text-[#8a8a99]">{v.face_px}px · yaw {v.yaw > 0 ? '+' : ''}{v.yaw ?? 0}°</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {cands.length > 0 && <p className="mt-3 text-[11px] text-[#8a8a99]">Pick only faces that clearly look like the same person. A drifted face in the fingerprint poisons every future score. Don't like any? Change the base/BIO in Step 1 and regenerate.</p>}
      </section>

      {/* STEP 3 — lock */}
      <section className="eve-panel">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          {step(3, 'lock the fingerprint')}
          <ScanFace className="h-4 w-4 text-[#4ea1ff]" />
          <span className="text-sm"><b>{entries.length}</b> face{entries.length !== 1 ? 's' : ''} · threshold {gallery?.threshold ?? '—'}</span>
          <div className="ml-auto flex gap-2">
            <button onClick={recalibrate} disabled={entries.length < 3}
              className="eve-button border border-[#353541] disabled:opacity-40">recalibrate threshold</button>
            <button onClick={reset} className="eve-button border border-[#5d2926] text-[#f18b84]">reset</button>
          </div>
        </div>
        {entries.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {entries.map((e) => {
              const y = gallery.meta?.[e]?.yaw
              return <span key={e} className="eve-chip">{e} {y > 0 ? '+' : ''}{y?.toFixed?.(0) ?? 0}°</span>
            })}
          </div>
        )}
        {result && <p className="mt-3 text-xs text-[#62d99d]">Recalibrated → threshold <b>{result.threshold}</b> (self-agreement mean {result.mean}, min {result.min}, {result.n_faces} faces)</p>}
        {entries.length < 3 && <p className="mt-2 text-[11px] text-[#8a8a99]">Add at least 3 approved faces, then recalibrate.</p>}
      </section>
    </main>
  )
}
