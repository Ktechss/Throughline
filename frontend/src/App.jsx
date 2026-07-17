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
  const [stamp, setStamp] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    const [p, r, g, pl] = await Promise.all([
      api.get('/api/parts'), api.get('/api/runs'),
      api.get('/api/gallery'), api.get('/api/poses'),
    ])
    setParts(p.parts); setRuns(r.runs); setGallery(g); setPoses(pl.poses)
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

  const mark = async (id, decision) => {
    await api.send(`/api/runs/${id}/mark`, 'POST', { decision })
    await refresh()
  }

  const addToGallery = async (id) => {
    const name = window.prompt('Gallery view name (front / side / three_quarter):', 'front')
    if (!name) return
    try {
      await api.send('/api/gallery', 'POST', { run_id: id, name })
      await refresh()
    } catch (e) { setErr(String(e)) }
  }

  const sections = [...new Set(parts.map((p) => p.section))]

  return (
    <div className="app">
      <header>
        <h1>eve1</h1>
        <nav>
          {['parts', 'pose', 'prompt', 'review'].map((t) => (
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
              refs: {refs.length ? refs.join(', ') : 'none'}
              {refs.length > 0 && <button className="ghost" onClick={() => setRefs([])}>clear</button>}
            </span>
          </div>
          <div className="grid">
            {runs.map((r) => {
              const v = r.verdict || {}
              return (
                <div key={r.id} className={`card ${r.mark || ''}`}>
                  <img alt={r.id} src={`/api/images/${r.file}`} />
                  <div className="verdict">
                    <span className={`st ${v.status}`}>{v.status}</span>
                    {v.similarity != null && <b>{v.similarity.toFixed(3)}</b>}
                    {v.yaw != null && <span className="meta">yaw {v.yaw > 0 ? '+' : ''}{v.yaw}°</span>}
                    {v.face_px != null && <span className="meta">{v.face_px}px</span>}
                    {v.low_confidence && <span className="tag warn">low signal</span>}
                  </div>
                  <div className="acts">
                    <button className={r.mark === 'approve' ? 'on' : ''} onClick={() => mark(r.id, 'approve')}>approve</button>
                    <button className={r.mark === 'reject' ? 'on' : ''} onClick={() => mark(r.id, 'reject')}>reject</button>
                    <button onClick={() => setRefs([r.file])}>use as ref</button>
                    <button onClick={() => addToGallery(r.id)}>→ gallery</button>
                  </div>
                </div>
              )
            })}
            {!runs.length && <p className="note">No generations yet.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
