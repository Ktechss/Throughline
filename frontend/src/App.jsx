import { useCallback, useEffect, useState } from 'react'
import Header from '@/components/eve/Header'
import Shoot from '@/components/eve/Shoot'
import Bio from '@/components/eve/Bio'
import Review from '@/components/eve/Review'
import Calibrate from '@/components/eve/Calibrate'
import VideoStudio from '@/components/eve/VideoStudio'
import OriginModal from '@/components/eve/OriginModal'
import OutfitDrawer from '@/components/eve/OutfitDrawer'
import { api, genView, mergeOutfit, STAGE } from '@/lib/eve'

export default function App() {
  const [tab, setTab] = useState('shoot')
  const [parts, setParts] = useState([])
  const [runs, setRuns] = useState([])
  const [gallery, setGallery] = useState({ entries: [] })
  const [availRefs, setAvailRefs] = useState([])
  const [importPath, setImportPath] = useState('')
  const [bio, setBio] = useState(null)
  const [brief, setBrief] = useState('')
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const [wardrobe, setWardrobe] = useState([])
  const [poseRefs, setPoseRefs] = useState([])
  const [outfit, setOutfit] = useState('')
  const [outfitText, setOutfitText] = useState('')
  const [describing, setDescribing] = useState(false)
  const [creating, setCreating] = useState(null)
  const [outfitPreview, setOutfitPreview] = useState(null)   // generated turnaround awaiting save/discard
  const [details, setDetails] = useState(null)   // structured outfit fields after a describe (null = hidden)
  const [outfitImageUrl, setOutfitImageUrl] = useState(null) // uploaded describe image (drawer preview)
  const [drawerOpen, setDrawerOpen] = useState(false)        // describe-outfit side drawer
  const [bodyCreating, setBodyCreating] = useState(null)     // body-ref generation status
  const [bodyPreview, setBodyPreview] = useState(null)       // generated body awaiting save/discard
  const [stamp, setStamp] = useState(0)                      // cache-buster for overwritten refs (body-canonical.png)
  const [poseRef, setPoseRef] = useState('')
  const [poseId, setPoseId] = useState('')                   // selected text-pose preset
  const [resolution, setResolution] = useState('4K')         // 1K | 2K | 4K
  const [poseLibrary, setPoseLibrary] = useState([])         // { id, text } presets
  const [bodies, setBodies] = useState([])                   // saved body-type library
  const [stats, setStats] = useState(null)                   // approval analytics + gold set
  const [cameraMoves, setCameraMoves] = useState({ moves: [], models: [] })
  const [videos, setVideos] = useState([])                   // generated clips
  const [videoBusy, setVideoBusy] = useState(null)           // current animate status
  const [generations, setGenerations] = useState([])
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    const [p, r, g, rf, b, wd, pr, bd, pl, stx, cm, vd] = await Promise.all([
      api.get('/api/parts'), api.get('/api/runs'), api.get('/api/gallery'),
      api.get('/api/refs'), api.get('/api/bio'), api.get('/api/wardrobe'),
      api.get('/api/pose-refs'), api.get('/api/bodies'), api.get('/api/pose-library'),
      api.get('/api/stats'), api.get('/api/camera-moves'), api.get('/api/videos'),
    ])
    setBodies(bd.bodies); setPoseLibrary(pl.poses); setStats(stx)
    setCameraMoves(cm); setVideos(vd.videos)
    setParts(p.parts); setRuns(r.runs); setGallery(g)
    setAvailRefs(rf.refs); setBio(b); setWardrobe(wd.wardrobe); setPoseRefs(pr.pose_refs)
    setStamp(Date.now())   // bust the cache for refs overwritten under a stable filename
  }, [])

  useEffect(() => { refresh().catch((e) => setErr(String(e))) }, [refresh])

  const savePart = async (id, patch) => {
    const next = parts.map((p) => (p.id === id ? { ...p, ...patch } : p))
    setParts(next)
    await api.send('/api/parts', 'PUT', { parts: next })
  }

  const pollGen = useCallback((jid) => {
    let alive = true
    const tick = async () => {
      if (!alive) return
      try {
        const st = await api.get(`/api/jobs/${jid}`)
        setGenerations((gs) => gs.map((g) => (g.jid === jid ? { ...g, status: st, run: st.run || g.run } : g)))
        if (st.done) { refresh().catch(() => {}); return }
      } catch { /* transient */ }
      setTimeout(tick, 1500)
    }
    tick()
  }, [refresh])

  const shoot = async () => {
    if (!bio?.reference) { setErr('No BIO reference — set one under bio › advanced · face.'); return }
    setErr(null)
    const label = brief.trim().slice(0, 40) || (outfit ? `outfit: ${outfit}` : 'untitled shot')
    // Optimistic card the INSTANT you click — no waiting on the network for feedback.
    const tmp = `tmp-${Date.now()}-${Math.round(Math.random() * 1e6)}`
    setGenerations((gs) => [{ jid: tmp, label, status: { stage: 'starting', elapsed: 0, done: false }, run: null }, ...gs])
    try {
      const { job: jid } = await api.send('/api/shot', 'POST', {
        brief, aspect: '3:4', prompt: aiPrompt.trim() || null,
        wardrobe_id: outfit || null, pose_ref_id: poseRef || null,
        pose_id: poseId || null, resolution,
      })
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, jid } : g)))   // swap tmp → real job id
      pollGen(jid)
    } catch (e) {
      setErr(String(e))
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, status: { done: true, error: String(e) } } : g)))
    }
  }

  const aiWrite = async () => {
    setAiBusy(true); setErr(null)
    try {
      const r = await api.send('/api/shot/ai-prompt', 'POST',
        { brief, wardrobe_id: outfit || null, pose_ref_id: poseRef || null, pose_id: poseId || null })
      setAiPrompt(r.prompt)
    } catch (e) { setErr(String(e)) } finally { setAiBusy(false) }
  }

  const describe = async (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    if (!f) return
    // Open the side drawer immediately with the uploaded image + a reading state.
    setOutfitImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(f) })
    setDrawerOpen(true); setDescribing(true); setErr(null)
    try {
      const d = await api.upload('/api/wardrobe/describe', f)
      setOutfitText(d.outfit)
      setDetails(d.details || {})
    } catch (e2) { setErr(String(e2)); setDrawerOpen(false) } finally { setDescribing(false) }
  }
  const setDetailField = (key, value) => setDetails((d) => ({ ...(d || {}), [key]: value }))

  // Generate the outfit turnaround, then PREVIEW it — no name asked up front.
  const createOutfit = async () => {
    setCreating('starting…'); setErr(null); setOutfitPreview(null)
    try {
      const { job: jid } = await api.send('/api/wardrobe/create', 'POST',
        { outfit: mergeOutfit(outfitText, details) })   // fold in the key details
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        const st = await api.get(`/api/jobs/${jid}`)
        setCreating(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(st.error); else setOutfitPreview(st.run); break }
      }
    } catch (e) { setErr(String(e)) } finally { setCreating(null) }
  }

  // Like the preview -> name it and save into the wardrobe.
  const saveOutfit = async () => {
    const name = window.prompt('Name this outfit:', '')
    if (!name) return
    try {
      await api.send('/api/wardrobe/from-run', 'POST', { run_id: outfitPreview.id, name })
      setOutfitPreview(null); setOutfitText(''); setDetails(null); await refresh()
    } catch (e) { setErr(String(e)) }
  }
  const discardOutfit = () => setOutfitPreview(null)

  // Generate a canonical body image (text-driven, no competing body ref) → preview.
  const createBodyRef = async () => {
    setBodyCreating('starting…'); setErr(null); setBodyPreview(null)
    try {
      const { job: jid } = await api.send('/api/bio/body-ref/create', 'POST', {})
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        const st = await api.get(`/api/jobs/${jid}`)
        setBodyCreating(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(st.error); else setBodyPreview(st.run); break }
      }
    } catch (e) { setErr(String(e)) } finally { setBodyCreating(null) }
  }
  // Save the generated body as a NAMED body type in the library, and make it active.
  const saveBodyRef = async () => {
    const name = window.prompt('Name this body type (e.g. "oversized", "48DDD", "slim"):', '')
    if (!name) return
    try {
      const { id } = await api.send('/api/bodies/save', 'POST', { run_id: bodyPreview.id, name })
      await api.send('/api/bodies/select', 'POST', { id })   // make it the active figure
      setBodyPreview(null); await refresh()
    } catch (e) { setErr(String(e)) }
  }
  const discardBodyRef = () => setBodyPreview(null)
  const selectBody = async (id) => {
    try { await api.send('/api/bodies/select', 'POST', { id }); await refresh() } catch (e) { setErr(String(e)) }
  }
  const deleteBody = async (id) => {
    try { await fetch(`/api/bodies/${id}`, { method: 'DELETE' }); await refresh() } catch (e) { setErr(String(e)) }
  }

  const uploadTo = (url) => async (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    if (!f) return
    try { await api.upload(url, f); await refresh() } catch (er) { setErr(String(er)) }
  }

  const mark = async (id, decision) => {
    try {
      await api.send(`/api/runs/${id}/mark`, 'POST', { decision })
      setDetail((d) => (d && d.id === id ? { ...d, mark: decision } : d))
      await refresh()
    } catch (e) { setErr(String(e)) }
  }
  const exportGold = async () => {
    try {
      const r = await api.send('/api/gold/export', 'POST', {})
      setErr(null); await refresh()
      window.alert(`Gold set exported: ${r.exported} approved shots → data/gold/ (${r.gold_on_disk} on disk). This is your LoRA dataset — the gallery stays frozen.`)
    } catch (e) { setErr(String(e)) }
  }
  const videoDirect = async (scenario) => {
    setErr(null)
    try { return await api.send('/api/video-direct', 'POST', { scenario }) }
    catch (e) { setErr(String(e)); throw e }
  }
  const animate = async (payload) => {
    setVideoBusy('starting…'); setErr(null)
    try {
      const { job: jid } = await api.send('/api/animate', 'POST', payload)
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000))
        const st = await api.get(`/api/jobs/${jid}`)
        setVideoBusy(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(String(st.error)); break }
      }
      await refresh()
    } catch (e) { setErr(String(e)) } finally { setVideoBusy(null) }
  }
  const purgeRejected = async () => {
    if (!window.confirm('Delete all rejected images from disk? This cannot be undone.')) return
    try {
      const r = await api.send('/api/runs/purge-rejected', 'POST', {})
      await refresh()
      window.alert(`Deleted ${r.deleted} rejected images · freed ${r.freed_mb} MB.`)
    } catch (e) { setErr(String(e)) }
  }
  const toWardrobe = async (id) => {
    const name = window.prompt('Save this outfit to the wardrobe as:', ''); if (!name) return
    try { await api.send('/api/wardrobe/from-run', 'POST', { run_id: id, name }); await refresh() } catch (e) { setErr(String(e)) }
  }
  const toPoseRef = async (id) => {
    const name = window.prompt('Save this as a pose reference named:', ''); if (!name) return
    try { await api.send('/api/pose-refs/from-run', 'POST', { run_id: id, name }); await refresh() } catch (e) { setErr(String(e)) }
  }

  const setBioRef = async (name) => {
    try { await api.send('/api/bio/reference', 'PUT', { reference: name }); await refresh() } catch (e) { setErr(String(e)) }
  }
  const toGallery = async (r) => {
    const view = window.prompt('Gallery view (front / side / three_quarter):', r.pose_class || 'front'); if (!view) return
    try { await api.send('/api/gallery/from-ref', 'POST', { name: r.name, view }); await refresh() } catch (e) { setErr(String(e)) }
  }
  const deleteRef = async (name) => {
    try { await fetch(`/api/refs/${name}`, { method: 'DELETE' }); await refresh() } catch (e) { setErr(String(e)) }
  }
  const importRef = async () => {
    try { await api.send('/api/refs/import', 'POST', { path: importPath }); setImportPath(''); await refresh() } catch (e) { setErr(String(e)) }
  }
  const resetParts = async () => {
    if (!window.confirm('Reset every part to defaults? Your edits are lost.')) return
    try { const r = await api.send('/api/parts/reset', 'POST', {}); setParts(r.parts) } catch (e) { setErr(String(e)) }
  }

  const gens = generations.map(genView)

  return (
    <div className="min-h-screen bg-[#0c0c0f] text-[#e6e6ea]">
      <Header tab={tab} setTab={setTab} count={runs.length} gallery={gallery} />

      {err && (
        <div onClick={() => setErr(null)}
          className="mx-auto mt-3 max-w-[1180px] cursor-pointer rounded-md border border-[#5d2926] bg-[#211313] px-4 py-2 text-xs text-[#f18b84]">
          {err} <span className="text-[#9b6764]">· click to dismiss</span>
        </div>
      )}

      {tab === 'shoot' && (
        <Shoot
          bio={bio} gens={gens} onOpen={setDetail} goBio={() => setTab('bio')}
          brief={brief} setBrief={setBrief} aiPrompt={aiPrompt} setAiPrompt={setAiPrompt}
          aiBusy={aiBusy} onAiPrompt={aiWrite} onGenerate={shoot}
          outfit={outfit} setOutfit={setOutfit} poseRef={poseRef} setPoseRef={setPoseRef}
          poseId={poseId} setPoseId={setPoseId} poseLibrary={poseLibrary}
          resolution={resolution} setResolution={setResolution}
          wardrobe={wardrobe} poseRefs={poseRefs}
          outfitText={outfitText} setOutfitText={setOutfitText}
          describing={describing} onDescribe={describe} creating={creating} onCreateOutfit={createOutfit}
          outfitPreview={outfitPreview} onSaveOutfit={saveOutfit} onDiscardOutfit={discardOutfit}
          onUploadOutfit={uploadTo('/api/wardrobe/upload')} onUploadPose={uploadTo('/api/pose-refs/upload')}
        />
      )}

      {tab === 'bio' && bio && (
        <Bio
          bio={bio} refs={availRefs} parts={parts}
          importPath={importPath} setImportPath={setImportPath}
          onImport={importRef} onUploadRef={uploadTo('/api/refs/upload')}
          onSetBio={setBioRef} onToGallery={toGallery} onDeleteRef={deleteRef}
          savePart={savePart} onResetParts={resetParts}
          bodyCreating={bodyCreating} bodyPreview={bodyPreview} stamp={stamp}
          bodies={bodies} onSelectBody={selectBody} onDeleteBody={deleteBody}
          onCreateBody={createBodyRef} onSaveBody={saveBodyRef} onDiscardBody={discardBodyRef}
        />
      )}

      {tab === 'calibrate' && (
        <Calibrate bio={bio} gallery={gallery} onRefresh={refresh}
          onEditBio={() => setTab('bio')}
          onUploadBase={async (e) => {
            const f = e.target.files?.[0]; e.target.value = ''
            if (!f) return
            try {
              const info = await api.upload('/api/refs/upload', f)
              if (!info.usable) { setErr('No face detected in that image — pick a clear face photo.'); return }
              await api.send('/api/bio/reference', 'PUT', { reference: info.name })
              await refresh()
            } catch (er) { setErr(String(er)) }
          }} />
      )}

      {tab === 'video' && <VideoStudio runs={runs} cameraMoves={cameraMoves.moves} models={cameraMoves.models} videos={videos} onAnimate={animate} onDirect={videoDirect} busy={videoBusy} stamp={stamp} />}

      {tab === 'review' && <Review runs={runs} onOpen={setDetail} onMark={mark} stats={stats} onExportGold={exportGold} onPurgeRejected={purgeRejected} />}

      <OutfitDrawer open={drawerOpen} imageUrl={outfitImageUrl} describing={describing}
        outfitText={outfitText} setOutfitText={setOutfitText} details={details} onDetail={setDetailField}
        creating={creating} onClose={() => setDrawerOpen(false)}
        onGenerate={() => { setDrawerOpen(false); createOutfit() }} />

      <OriginModal run={detail} wardrobe={wardrobe} poseRefs={poseRefs}
        onClose={() => setDetail(null)} onMark={mark} onToWardrobe={toWardrobe} onToPoseRef={toPoseRef} />
    </div>
  )
}
