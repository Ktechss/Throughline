import { useCallback, useEffect, useState } from 'react'
import PoseEditor from './PoseEditor'
import './App.css'

const api = {
  async get(u) { const r = await fetch(u); if (!r.ok) throw new Error(await r.text()); return r.json() },
  async send(u, method, body) {
    const r = await fetch(u, {
      method, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.text()).slice(0, 300))
    return r.json()
  },
}

const PROG_LABEL = {
  starting: 'Starting…',
  generating: 'Generating the image…',
  'moderation retry': 'Moderation flagged it — retrying automatically…',
  downloading: 'Downloading…',
  'leveling & gating': 'Straightening & checking identity…',
  done: 'Done',
  failed: 'Failed',
}

const SECTION_HELP = {
  face: 'Seed hunt only. Once a reference image exists these are dropped automatically — describing a face measured 0.834 against 0.860 for a terse "don\'t change her".',
  skin: 'Photographic facts, never adjectives. A model can render a fact; it cannot render a wish.',
  pose: 'The pose reference IMAGE carries this. Text pose control returned frontal on 3 of 4 probes.',
  camera: 'The highest-leverage line in the prompt. Depth-of-field and studio light are what make an image read as AI.',
}

export default function App() {
  const [tab, setTab] = useState('parts')
  const [parts, setParts] = useState([])
  const [pose, setPose] = useState(null)
  const [poseName, setPoseName] = useState('standing')
  const [poses, setPoses] = useState([])
  const [preview, setPreview] = useState(null)
  const [runs, setRuns] = useState([])
  const [gallery, setGallery] = useState({ entries: [] })
  const [hasRef, setHasRef] = useState(false)
  const [usePoseImg, setUsePoseImg] = useState(true)
  const [refs, setRefs] = useState([])
  const [availRefs, setAvailRefs] = useState([])
  const [importPath, setImportPath] = useState('')
  const [bio, setBio] = useState(null)
  const [brief, setBrief] = useState('')
  const [shotPrompt, setShotPrompt] = useState(null)
  const [withPose, setWithPose] = useState(false)
  const [job, setJob] = useState(null)
  const [stamp, setStamp] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    const [p, r, g, pl, rf, b] = await Promise.all([
      api.get('/api/parts'), api.get('/api/runs'),
      api.get('/api/gallery'), api.get('/api/poses'), api.get('/api/refs'),
      api.get('/api/bio'),
    ])
    setParts(p.parts); setRuns(r.runs); setGallery(g); setPoses(pl.poses)
    setAvailRefs(rf.refs); setBio(b)
  }, [])

  useEffect(() => { refresh().catch((e) => setErr(String(e))) }, [refresh])

  useEffect(() => {
    api.get(`/api/poses/${poseName}`).then(setPose).catch(() => {
      api.get('/api/skeleton/default').then((d) => setPose(d.pose))
    })
  }, [poseName])

  useEffect(() => {
    if (!parts.length) return
    api.send('/api/compose', 'POST', { has_reference: hasRef, pose_name: poseName })
      .then(setPreview).catch((e) => setErr(String(e)))
  }, [parts, hasRef, poseName])

  const savePart = async (id, patch) => {
    const next = parts.map((p) => (p.id === id ? { ...p, ...patch } : p))
    setParts(next)
    await api.send('/api/parts', 'PUT', { parts: next })
  }

  const savePose = async () => {
    await api.send(`/api/poses/${poseName}`, 'PUT', pose)
    setPoses((ps) => (ps.includes(poseName) ? ps : [...ps, poseName]))
    setStamp(Date.now())
  }

  const generate = async () => {
    setBusy(true); setErr(null)
    try {
      await savePose()
      await api.send('/api/generate', 'POST', {
        pose_name: poseName, use_pose_image: usePoseImg, refs, aspect: '4:5',
      })
      await refresh()
      setTab('review')
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const shoot = async () => {
    setBusy(true); setErr(null)
    setJob({ stage: 'starting', elapsed: 0 })
    try {
      if (withPose) await savePose()
      const { job: jid } = await api.send('/api/shot', 'POST', {
        brief, pose_name: withPose ? poseName : null,
        use_pose_image: withPose, aspect: '3:4',
      })
      // Poll live status until done, so the user sees stage + elapsed time
      // instead of a dead button.
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        const st = await api.get(`/api/jobs/${jid}`)
        setJob(st)
        if (st.done) {
          if (st.error) setErr(st.error)
          await refresh()
          if (!st.error) setTab('review')
          break
        }
      }
    } catch (e) { setErr(String(e)) } finally { setBusy(false); setJob(null) }
  }

  const mark = async (id, decision) => {
    await api.send(`/api/runs/${id}/mark`, 'POST', { decision })
    await refresh()
  }

  const sections = [...new Set(parts.map((p) => p.section))]

  // Group runs into sessions, newest first. /api/runs is already newest-first,
  // so insertion order preserves that and Map keeps it.
  const sessions = [...runs.reduce((m, r) => {
    const id = r.session?.id || 'ungrouped'
    return m.set(id, [...(m.get(id) || []), r])
  }, new Map())]

  return (
    <div className="app">
      <header>
        <h1>eve1</h1>
        <nav>
          {['shoot', 'bio', 'face', 'parts', 'pose', 'review'].map((t) => (
            <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
              {t}{t === 'review' && runs.length ? ` (${runs.length})` : ''}
            </button>
          ))}
        </nav>
        <div className="gal">
          gallery: {gallery.entries.length ? gallery.entries.join(', ') : <em>empty — ungated</em>}
        </div>
      </header>

      {err && <div className="err" onClick={() => setErr(null)}>{err}</div>}

      {tab === 'shoot' && (
        <div className="pane">
          <div className="bio-chip">
            <span>BIO</span>
            {bio?.reference
              ? <><img alt="ref" src={`/api/refs/${bio.reference}/file`} />
                  <b>{bio.reference}</b>
                  <span className="meta">
                    {bio.reference_face?.face_px}px · {bio.gallery?.entries.length} gallery angles
                    · gate {bio.gallery?.threshold}
                  </span>
                  <span className="meta">attached to every shot</span></>
              : <b className="warnfg">no BIO reference — set one on the face tab</b>}
          </div>

          <textarea
            className="brief" rows={5} value={brief}
            placeholder={"What's the shot? Place, moment, pose, wardrobe, light.\n\n" +
              "e.g. Walking through Shahpur Jat late morning, caught mid-stride " +
              "glancing back over her shoulder, fabric swatches under one arm. " +
              "Rust linen kurta, indigo jeans. The lane is in shadow but the wall " +
              "above catches hard sun."}
            onChange={(e) => setBrief(e.target.value)}
          />
          <div className="row">
            <button className="gen" disabled={busy || !bio?.reference} onClick={shoot}>
              {busy ? 'generating…' : 'generate'}
            </button>
            <label><input type="checkbox" checked={withPose}
              onChange={(e) => setWithPose(e.target.checked)} /> use pose rig ({poseName})</label>
            <button className="ghost" onClick={async () => {
              const p = await api.send('/api/shot/preview', 'POST',
                { brief, pose_name: withPose ? poseName : null })
              setShotPrompt(p)
            }}>preview prompt</button>
          </div>

          {job && (
            <div className="progress">
              <div className="spinner" />
              <div className="pstage">
                <b>{PROG_LABEL[job.stage] || job.stage}</b>
                {job.retry ? <span className="tag warn">moderation retry {job.retry}/4</span> : null}
                <div className="note">
                  {Math.round(job.elapsed || 0)}s elapsed
                  {' · '}gpt-image-2 usually takes 60–150s
                </div>
              </div>
            </div>
          )}

          <p className="note">
            You write the shot. Who she is comes from the BIO and the reference
            image, identically every time — so two photos a month apart differ
            only in the ways you meant them to. Every shot is straightened and
            identity-checked before you see it.
          </p>
          {shotPrompt?.sanitised?.length > 0 && (
            <div className="lint info">
              Sanitised {shotPrompt.sanitised.length} phrase{shotPrompt.sanitised.length > 1 ? 's' : ''} before
              sending, to lower the chance of a moderation refusal:
              <ul className="san">
                {shotPrompt.sanitised.map((c, i) => (
                  <li key={i}><code>{c.was}</code> → <code>{c.now}</code> <span className="meta">({c.why})</span></li>
                ))}
              </ul>
            </div>
          )}
          {shotPrompt && (
            <>
              <h4>final prompt ({shotPrompt.chars} chars)</h4>
              <pre className="final">{shotPrompt.prompt}</pre>
            </>
          )}
        </div>
      )}

      {tab === 'bio' && bio && (
        <div className="pane">
          <p className="help">
            Locked. This is who Kiara is, attached to every generation. Her face
            is carried by the reference image, not by words — {bio.dropped_identity_parts?.length}{' '}
            description parts are dropped automatically, because describing a
            face measured 0.834 against 0.860 for a terse "don't change her".
            Edit these on the <b>parts</b> tab only if you mean to change the
            character.
          </p>
          <div className="row top">
            {bio.reference && (
              <div className="rendered">
                <h4>identity reference</h4>
                <img alt="bio ref" src={`/api/refs/${bio.reference}/file`} />
                <p className="note">
                  {bio.reference} · {bio.reference_face?.face_px}px ·{' '}
                  {bio.reference_face?.pose_class}
                </p>
              </div>
            )}
            <div style={{ flex: 1, minWidth: 320 }}>
              <h4>identity lock</h4>
              <pre className="final sys">{bio.identity_lock}</pre>
              <h4>gate</h4>
              <p className="note">
                {bio.gallery.entries.map((e) => (
                  <span key={e} className="tag ident" style={{ marginRight: 6 }}>
                    {e} {bio.gallery.meta?.[e]?.yaw > 0 ? '+' : ''}
                    {bio.gallery.meta?.[e]?.yaw?.toFixed?.(0)}°
                  </span>
                ))}
                <br />threshold {bio.gallery.threshold} — her own frontals agree at 0.797
              </p>
            </div>
          </div>
          {Object.entries(bio.sections).map(([sec, ps]) => (
            <section key={sec}>
              <h3>{sec}</h3>
              {ps.map((p) => (
                <div key={p.id} className="part locked">
                  <div className="part-head">
                    <strong>{p.label}</strong>
                    {p.critical && <span className="tag crit">load-bearing</span>}
                    <code>{p.id}</code>
                  </div>
                  <pre className="biotext">{p.text}</pre>
                  {p.note && <p className="note">{p.note}</p>}
                </div>
              ))}
            </section>
          ))}
        </div>
      )}

      {tab === 'face' && (
        <div className="pane">
          <p className="help">
            An identity reference does two different jobs. As a <b>generation
            ref</b> it tells the model who to draw. In the <b>gallery</b> it
            tells the gate whether the model obeyed. Set both from the same
            image and you find out.
          </p>
          <div className="row">
            <input className="grow" placeholder="C:\path\to\face.png" value={importPath}
              onChange={(e) => setImportPath(e.target.value)} />
            <button onClick={async () => {
              try { await api.send('/api/refs/import', 'POST', { path: importPath }); setImportPath(''); await refresh() }
              catch (e) { setErr(String(e)) }
            }}>import</button>
            <label className="upl">
              upload
              <input type="file" accept="image/*" hidden onChange={async (e) => {
                const f = e.target.files?.[0]; if (!f) return
                const fd = new FormData(); fd.append('file', f)
                const r = await fetch('/api/refs/upload', { method: 'POST', body: fd })
                if (!r.ok) setErr((await r.text()).slice(0, 200)); else await refresh()
                e.target.value = ''
              }} />
            </label>
          </div>
          <div className="grid">
            {availRefs.map((r) => (
              <div key={r.name} className={`card ${refs.includes(r.name) ? 'approve' : ''}`}>
                <img alt={r.name} src={`/api/refs/${r.name}/file`} />
                <div className="verdict">
                  <span className={`st ${r.usable ? 'kept' : 'rejected'}`}>
                    {r.usable ? r.pose_class : 'no face'}
                  </span>
                  {r.face_px != null && <span className="meta">{r.face_px}px</span>}
                  {r.yaw != null && <span className="meta">yaw {r.yaw > 0 ? '+' : ''}{r.yaw}°</span>}
                </div>
                <div className="acts">
                  <button className={refs.includes(r.name) ? 'on' : ''}
                    onClick={() => { setRefs([r.name]); setHasRef(true) }}>
                    use as face ref
                  </button>
                  <button onClick={async () => {
                    const view = window.prompt('Gallery view (front / side / three_quarter):', r.pose_class || 'front')
                    if (!view) return
                    try { await api.send('/api/gallery/from-ref', 'POST', { name: r.name, view }); await refresh() }
                    catch (e) { setErr(String(e)) }
                  }}>→ gallery</button>
                  <button className="ghost" onClick={async () => {
                    await fetch(`/api/refs/${r.name}`, { method: 'DELETE' }); await refresh()
                  }}>delete</button>
                </div>
              </div>
            ))}
            {!availRefs.length && <p className="note">
              No identity references yet. Import one — until then every generation
              invents a face from the text, which is what "words cannot specify a
              person" means in practice.
            </p>}
          </div>
        </div>
      )}

      {tab === 'parts' && (
        <div className="pane">
          {sections.map((s) => (
            <section key={s}>
              <h3>{s}</h3>
              {SECTION_HELP[s] && <p className="help">{SECTION_HELP[s]}</p>}
              {parts.filter((p) => p.section === s).map((p) => (
                <div key={p.id} className={`part ${p.enabled ? '' : 'off'}`}>
                  <div className="part-head">
                    <label>
                      <input type="checkbox" checked={p.enabled}
                        onChange={(e) => savePart(p.id, { enabled: e.target.checked })} />
                      <strong>{p.label}</strong>
                    </label>
                    {p.critical && <span className="tag crit">load-bearing</span>}
                    {p.identity && <span className="tag ident">identity</span>}
                    <code>{p.id}</code>
                  </div>
                  <textarea
                    value={p.text} rows={p.text.length > 120 ? 4 : 2}
                    onChange={(e) => setParts(parts.map((q) => (q.id === p.id ? { ...q, text: e.target.value } : q)))}
                    onBlur={(e) => savePart(p.id, { text: e.target.value })}
                  />
                  {p.note && <p className="note">{p.note}</p>}
                </div>
              ))}
            </section>
          ))}
          <button className="ghost" onClick={async () => {
            if (!window.confirm('Reset every part to defaults? Your edits are lost.')) return
            const r = await api.send('/api/parts/reset', 'POST', {}); setParts(r.parts)
          }}>reset to defaults</button>
        </div>
      )}

      {tab === 'pose' && pose && (
        <div className="pane">
          <div className="row">
            <select value={poses.includes(poseName) ? poseName : ''} onChange={(e) => e.target.value && setPoseName(e.target.value)}>
              <option value="">— saved poses —</option>
              {poses.map((p) => <option key={p}>{p}</option>)}
            </select>
            <input value={poseName} onChange={(e) => setPoseName(e.target.value)} placeholder="pose name" />
            <button onClick={savePose}>save pose</button>
          </div>
          <div className="row top">
            <PoseEditor pose={pose} onChange={setPose} />
            <div className="rendered">
              <h4>what the model sees</h4>
              <img alt="pose reference" src={`/api/poses/${poseName}/preview.png?t=${stamp}`} />
              <p className="note">Save the pose to refresh this. It is the actual
                reference image, not a preview of one.</p>
            </div>
          </div>
        </div>
      )}

      {tab === 'prompt' && preview && (
        <div className="pane">
          <div className="row">
            <label><input type="checkbox" checked={hasRef} onChange={(e) => setHasRef(e.target.checked)} />
              a reference image is in play</label>
            <span className="note">{preview.chars} chars</span>
          </div>
          {preview.dropped?.length > 0 && (
            <div className="info">
              Dropped {preview.dropped.length} identity parts because a reference is in play:{' '}
              <code>{preview.dropped.join(', ')}</code>
            </div>
          )}
          {preview.lint?.map((l, i) => (
            <div key={i} className={`lint ${l.level}`}><code>{l.id}</code> {l.msg}</div>
          ))}
          <h4>system</h4>
          <pre className="final sys">{preview.system}</pre>
          <h4>final prompt</h4>
          <pre className="final">{preview.prompt}</pre>
        </div>
      )}

      {tab === 'review' && (
        <div className="pane">
          <div className="row">
            <label><input type="checkbox" checked={usePoseImg} onChange={(e) => setUsePoseImg(e.target.checked)} />
              send pose as a reference image</label>
            <button disabled={busy} onClick={generate}>{busy ? 'generating…' : 'generate'}</button>
            <span className="note">
              face ref: {refs.length ? <b>{refs.join(', ')}</b> : 'none'}
              {refs.length > 0 && <button className="ghost" onClick={() => { setRefs([]); setHasRef(false) }}>clear</button>}
            </span>
          </div>
          {!refs.length && (
            <div className="lint warn">
              No face reference — the model will invent a face from the text
              description, and it will invent a different one on every seed.
              Set one on the <b>face</b> tab.
            </div>
          )}
          {refs.length > 0 && usePoseImg && (
            <div className="lint info">
              Two references in play (face + pose). Three references measured
              0.547 against one reference's 0.811, so the pose image may be
              costing identity. Unmeasured here — check the score against a
              pose-off run before trusting it.
            </div>
          )}
          {sessions.map(([sid, group]) => {
            const s = group[0].session || {}
            const scored = group.filter((r) => r.verdict?.similarity != null)
            const best = scored.length
              ? Math.max(...scored.map((r) => r.verdict.similarity)) : null
            return (
              <section key={sid} className="session">
                <div className="session-head">
                  <strong>{s.label || 'untitled run'}</strong>
                  <span className="meta">{group.length} image{group.length > 1 ? 's' : ''}</span>
                  {best != null && <span className="meta">best {best.toFixed(3)}</span>}
                  <span className="meta">{(s.started || '').replace('T', ' ').slice(0, 16)}</span>
                  <code>{sid}</code>
                </div>
                <div className="grid">
                  {group.map((r) => {
                    const v = r.verdict || {}
                    return (
                      <div key={r.id} className={`card ${r.mark || ''}`}>
                        <img alt={r.id} src={`/api/images/${r.file}`} />
                        <div className="verdict">
                          <span className={`st ${v.status}`}>{v.status}</span>
                          {/* struck through when the comparison isn't fair: the
                              number is real, it just isn't about identity */}
                          {v.similarity != null && (
                            <b className={v.pose_mismatch ? 'void' : ''}>{v.similarity.toFixed(3)}</b>
                          )}
                          {v.yaw != null && (
                            <span className="meta">
                              yaw {v.yaw > 0 ? '+' : ''}{v.yaw}°
                              {v.source_yaw != null && <> vs ref {v.source_yaw > 0 ? '+' : ''}{v.source_yaw}°</>}
                            </span>
                          )}
                          {v.face_px != null && <span className="meta">{v.face_px}px</span>}
                          {v.roll != null && (
                            <span className="meta" title="head tilt after auto-leveling">
                              tilt {v.roll > 0 ? '+' : ''}{v.roll}°{v.tilted ? ' ⚠' : ''}
                            </span>
                          )}
                          {r.auto_leveled ? <span className="meta" title="straightened automatically">leveled {r.auto_leveled}°</span> : null}
                          {v.low_confidence && <span className="tag warn">low signal</span>}
                          {v.pose_mismatch && <span className="tag warn">pose mismatch</span>}
                        </div>
                        {v.reason && <p className="why">{v.reason}</p>}
                        <p className="prov">
                          {(r.endpoint || '').replace('fal-ai/', '')}
                          {r.refs?.length ? ` · ${r.refs.join(' + ')}` : ' · no ref'}
                        </p>
                        <div className="acts">
                          <button className={r.mark === 'approve' ? 'on' : ''} onClick={() => mark(r.id, 'approve')}>approve</button>
                          <button className={r.mark === 'reject' ? 'on' : ''} onClick={() => mark(r.id, 'reject')}>reject</button>
                          {/* No "-> gallery" here on purpose: the gallery is
                              seeded only from data/refs, so our own output can
                              never become the yardstick it is measured against. */}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )
          })}
          {!runs.length && <p className="note">No generations yet.</p>}
        </div>
      )}
    </div>
  )
}
