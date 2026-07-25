import { useCallback, useEffect, useRef, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import Header from '@/components/eve/Header'
import Landing from '@/components/eve/Landing'
import Shoot from '@/components/eve/Shoot'
import Bio from '@/components/eve/Bio'
import Review from '@/components/eve/Review'
import Calibrate from '@/components/eve/Calibrate'
import VideoStudio from '@/components/eve/VideoStudio'
import OriginModal from '@/components/eve/OriginModal'
import OutfitDrawer from '@/components/eve/OutfitDrawer'
import { api, genView, mergeOutfit, STAGE } from '@/lib/eve'

export default function App() {
  const [view, setView] = useState('landing')          // 'landing' (profile picker) | 'studio'
  const [characters, setCharacters] = useState([])
  const [activeChar, setActiveChar] = useState(null)   // { id, name }
  const [loading, setLoading] = useState(false)        // studio data loading after a switch
  const [buildStage, setBuildStage] = useState(null)   // guided-creation progress label
  const switchEpoch = useRef(0)                         // bumped on every character switch;
                                                        // in-flight polls bail when it changes
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
  const [drawerOpen, setDrawerOpen] = useState(false)        // outfit designer side drawer
  const [idea, setIdea] = useState('')                       // short outfit idea for the AI expander
  const [pickers, setPickers] = useState({})                 // occasion/style/fabric/silhouette/formality/season
  const [enriching, setEnriching] = useState(false)          // write-outfit (enrich) in progress
  const [saveCategory, setSaveCategory] = useState('')       // category the outfit saves into (auto-named)
  const [bodyCreating, setBodyCreating] = useState(null)     // body-ref generation status
  const [bodyPreview, setBodyPreview] = useState(null)       // generated body awaiting save/discard
  const [stamp, setStamp] = useState(0)                      // cache-buster for overwritten refs (body-canonical.png)
  const [poseRef, setPoseRef] = useState('')
  const [poseId, setPoseId] = useState('')                   // selected text-pose preset
  const [resolution, setResolution] = useState('4K')         // 1K | 2K | 4K
  const [faceAcc, setFaceAcc] = useState(true)               // render outfit's face-worn items (sunglasses/hats)
  const [poseLibrary, setPoseLibrary] = useState([])         // { id, text } presets
  const [bodies, setBodies] = useState([])                   // saved body-type library
  const [stats, setStats] = useState(null)                   // approval analytics + gold set
  const [cameraMoves, setCameraMoves] = useState({ moves: [], models: [] })
  const [videos, setVideos] = useState([])                   // generated clips
  const [videoBusy, setVideoBusy] = useState(null)           // current animate status
  const [makeBusy, setMakeBusy] = useState(null)             // make-video status
  const [generations, setGenerations] = useState([])
  const [calibCands, setCalibCands] = useState([])   // calibration faces — app-level so tab switches don't lose them
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

  const loadChars = useCallback(async () => {
    const r = await api.get('/api/characters')
    setCharacters(r.characters)
    setActiveChar(r.characters.find((c) => c.id === r.active) || null)
    return r
  }, [])

  // First screen is the profile picker — load the roster, don't auto-enter a studio.
  useEffect(() => { loadChars().catch((e) => setErr(String(e))) }, [loadChars])

  // Wipe ALL per-character client state so nothing bleeds across profiles — the
  // live generation queue especially, which is client-only and never refetched.
  const clearStudio = () => {
    switchEpoch.current += 1     // invalidate every in-flight poll (gen/body/outfit/video/build)
    setGenerations([]); setCalibCands([]); setDetail(null)
    setRuns([]); setBio(null); setWardrobe([]); setGallery({ entries: [] })
    setVideos([]); setStats(null); setPoseRefs([]); setBodies([]); setParts([])
    setOutfit(''); setPoseRef(''); setPoseId(''); setBrief(''); setAiPrompt('')
    setOutfitPreview(null); setBodyPreview(null); setOutfitImageUrl(null)
    setDrawerOpen(false); setDetails(null); setIdea(''); setPickers({})
    // reset every busy/spinner flag so none lingers on the next profile
    setAiBusy(false); setDescribing(false); setCreating(null); setBodyCreating(null)
    setVideoBusy(null); setMakeBusy(null); setEnriching(false)
  }

  const enterCharacter = async (id) => {
    setErr(null)
    clearStudio()           // no cross-character contamination
    setActiveChar(characters.find((c) => c.id === id) || { id, name: id })
    setTab('shoot')
    setView('studio')       // switch INSTANTLY — the overlay covers the data load
    setLoading(true)
    try {
      await api.send('/api/characters/active', 'PUT', { id })
      await refresh()
      await loadCalib()   // load her saved calibration faces into app-level state
    } catch (e) { setErr(String(e)) } finally { setLoading(false) }
  }

  const BUILD_LABEL = (stage) => (
    stage === 'writing bio' ? 'Writing her bio…'
      : stage === 'generating body' ? 'Generating her body…'
        : (stage === 'generating face' || stage === 'generating' || stage === 'starting') ? 'Generating her first face…'
          : (stage === 'gating') ? 'Checking her face…'
            : /retry/i.test(stage || '') ? 'Retrying (moderation)…'
              : 'Building her…')

  const pollBuild = (jid) => new Promise((resolve) => {
    const epoch = switchEpoch.current
    const tick = async () => {
      if (epoch !== switchEpoch.current) { resolve(null); return }   // switched away
      try {
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) { resolve(null); return }
        setBuildStage(BUILD_LABEL(st.stage))
        if (st.done) {
          if (st.error) setErr(st.error)
          resolve(st); return
        }
      } catch { /* transient */ }
      setTimeout(tick, 1200)
    }
    tick()
  })

  const createCharacter = async ({ name, description, face_shape, build, height_cm, file }) => {
    setErr(null)
    clearStudio()                     // start her studio clean
    setActiveChar({ id: '', name })   // optimistic label for the overlay
    setTab('calibrate')               // land where she gets calibrated
    setView('studio')
    setLoading(true); setBuildStage(file ? 'Generating her face from your image…' : 'Writing her bio…')
    try {
      const fd = new FormData()
      fd.append('name', name)
      fd.append('description', description || '')
      fd.append('face_shape', face_shape || '')
      fd.append('build', build || '')
      fd.append('height_cm', height_cm || '')
      if (file) fd.append('reference', file)
      const r = await fetch('/api/characters/guided', { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.text()).slice(0, 300))
      const { character, job } = await r.json()   // Claude writes bio → generates face → sets seed
      setActiveChar(character)
      await pollBuild(job)
      await refresh()
    } catch (e) { setErr(String(e)); setView('landing') } finally { setLoading(false); setBuildStage(null) }
  }

  const deleteCharacter = async (c) => {
    if (!window.confirm(`Delete "${c.name}" and all of her images, wardrobe and generations? This cannot be undone.`)) return
    try { await api.send(`/api/characters/${c.id}`, 'DELETE'); await loadChars() }
    catch (e) { setErr(String(e)) }
  }

  // A generation whose result the user must still SAVE (outfit / body preview) or
  // that is mid-build — switching away loses it from the UI (it's still recorded
  // to this character, but the preview/save step is gone). Warn before leaving.
  const generationInProgress = () =>
    !!creating || !!bodyCreating || !!buildStage || aiBusy || !!videoBusy || !!makeBusy
      || generations.some((g) => g.status && !g.status.done)

  const backToLanding = () => {
    if (generationInProgress() && !window.confirm(
      'A generation is still in progress. If you switch characters now, its preview '
      + 'will be lost (the finished result is still saved to this character). Switch anyway?'))
      return
    clearStudio(); setView('landing'); loadChars().catch((e) => setErr(String(e)))
  }

  const savePart = async (id, patch) => {
    const next = parts.map((p) => (p.id === id ? { ...p, ...patch } : p))
    setParts(next)
    await api.send('/api/parts', 'PUT', { parts: next })
  }

  const pollGen = useCallback((jid) => {
    const epoch = switchEpoch.current
    let alive = true
    const tick = async () => {
      if (!alive || epoch !== switchEpoch.current) return   // switched character — stop
      try {
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
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
        pose_id: poseId || null, resolution, face_accessories: faceAcc,
      })
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, jid } : g)))   // swap tmp → real job id
      pollGen(jid)
    } catch (e) {
      setErr(String(e))
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, status: { done: true, error: String(e) } } : g)))
    }
  }

  const aiWrite = async () => {
    const epoch = switchEpoch.current
    setAiBusy(true); setErr(null)
    try {
      const r = await api.send('/api/shot/ai-prompt', 'POST',
        { brief, wardrobe_id: outfit || null, pose_ref_id: poseRef || null, pose_id: poseId || null })
      if (epoch !== switchEpoch.current) return
      setAiPrompt(r.prompt)
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setAiBusy(false) }
  }

  const describe = async (e) => {
    const f = e.target.files?.[0]; e.target.value = ''
    if (!f) return
    const epoch = switchEpoch.current
    // Open the side drawer immediately with the uploaded image + a reading state.
    setOutfitImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(f) })
    setDrawerOpen(true); setDescribing(true); setErr(null)
    try {
      const d = await api.upload('/api/wardrobe/describe', f)
      if (epoch !== switchEpoch.current) return
      setOutfitText(d.outfit)
      setDetails(d.details || {})
    } catch (e2) { if (epoch === switchEpoch.current) { setErr(String(e2)); setDrawerOpen(false) } }
    finally { if (epoch === switchEpoch.current) setDescribing(false) }
  }
  const setDetailField = (key, value) => setDetails((d) => ({ ...(d || {}), [key]: value }))

  // Generate the outfit turnaround, then PREVIEW it — no name asked up front.
  const createOutfit = async () => {
    const epoch = switchEpoch.current
    setCreating('starting…'); setErr(null); setOutfitPreview(null)
    try {
      const { job: jid } = await api.send('/api/wardrobe/create', 'POST',
        { outfit: mergeOutfit(outfitText, details) })   // fold in the key details
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        if (epoch !== switchEpoch.current) return   // switched away — don't leak into the other profile
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
        setCreating(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(st.error); else setOutfitPreview(st.run); break }
      }
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setCreating(null) }
  }

  // Save the preview into a CATEGORY — the backend auto-names it <Category><next#>
  // (no manual name), and a unique name is enforced so a save can never overwrite
  // or desync another outfit.
  const saveOutfit = async () => {
    const category = (saveCategory || '').trim()
    if (!category) { setErr('Pick a category before saving.'); return }
    try {
      const r = await api.send('/api/wardrobe/from-run', 'POST',
        { run_id: outfitPreview.id, category })
      setOutfitPreview(null); setOutfitText(''); setDetails(null)
      setOutfit(r.id)   // auto-select the newly saved outfit
      await refresh()
    } catch (e) { setErr(String(e)) }
  }
  const discardOutfit = () => setOutfitPreview(null)

  // Open the outfit designer from scratch (no uploaded image, no describe-details)
  // so it shows the idea box + pickers for a fresh AI-written outfit.
  const openDesigner = () => { setDetails(null); setOutfitImageUrl(null); setDrawerOpen(true) }
  const setPicker = (key, value) => setPickers((p) => ({ ...p, [key]: value }))
  // Claude expands the idea + picks into a rich, opaque garment description → fills
  // the editable outfit box. Mirrors aiWrite; epoch-guarded against a mid-write switch.
  const enrichOutfit = async () => {
    const epoch = switchEpoch.current
    setEnriching(true); setErr(null)
    try {
      // base = the current description (from a described image or typed) → enriched.
      const r = await api.send('/api/wardrobe/enrich', 'POST', { base: outfitText, idea, ...pickers })
      if (epoch !== switchEpoch.current) return
      setOutfitText(r.outfit)
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setEnriching(false) }
  }

  // --- calibration faces, lifted to APP level so switching tabs (or characters)
  //     never throws away the generation. They live here exactly like the shot
  //     queue, and polling continues across tab mounts. ---
  const loadCalib = useCallback(async () => {
    try {
      const { candidates } = await api.get('/api/calibrate/candidates')
      setCalibCands((candidates || []).map((c) => ({ jid: c.id, id: c.id, file: c.file, angle: c.angle, verdict: c.verdict })))
    } catch { setCalibCands([]) }
  }, [])

  const pollCalib = (jid) => {
    const epoch = switchEpoch.current
    const tick = async () => {
      if (epoch !== switchEpoch.current) return
      try {
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
        if (st.done) {
          setCalibCands((cs) => cs.map((c) => (c.jid === jid
            ? (st.error ? { ...c, running: false, error: String(st.error).slice(0, 100) }
              : { ...c, running: false, id: st.run.id, file: st.run.file, verdict: st.run.verdict })
            : c)))
          return
        }
        setCalibCands((cs) => cs.map((c) => (c.jid === jid ? { ...c, stage: STAGE[st.stage] || st.stage } : c)))
      } catch { /* transient */ }
      setTimeout(tick, 2000)
    }
    tick()
  }

  const generateCalibFaces = async (count) => {
    setErr(null)
    try {
      const { jobs } = await api.send('/api/calibrate/faces', 'POST', { count })
      // prepend running cards; keep any already-loaded faces below
      setCalibCands((cs) => [...jobs.map((j) => ({ jid: j.job, angle: j.angle, running: true })), ...cs])
      jobs.forEach((j) => pollCalib(j.job))
    } catch (e) { setErr(String(e)) }
  }

  const toggleCalib = (jid) => setCalibCands((cs) => cs.map((c) => (c.jid === jid ? { ...c, sel: !c.sel } : c)))

  const addCalibToGallery = async () => {
    const sel = calibCands.filter((c) => c.sel && c.id)
    if (!sel.length) { setErr('Select at least one on-model face first.'); return }
    try {
      for (const c of sel) await api.send('/api/calibrate/gallery/add', 'POST', { run_id: c.id, view: c.angle })
      await refresh()
    } catch (e) { setErr(String(e)) }
  }

  const setCalibIdentity = async (runId) => {
    setErr(null)
    try { await api.send('/api/bio/reference/from-run', 'POST', { run_id: runId, name: 'identity' }); await refresh() }
    catch (e) { setErr(String(e)) }
  }

  // Generate a canonical body image (text-driven, no competing body ref) → preview.
  // Upload a body-SHAPE reference (no face required); returns { name }.
  const uploadShape = async (f) => await api.upload('/api/bio/shape-ref/upload', f)
  const createBodyRef = async (shapeRef, shape) => {
    const epoch = switchEpoch.current   // this body belongs to the character active NOW
    setBodyCreating('starting…'); setErr(null); setBodyPreview(null)
    try {
      const body = {}
      if (shapeRef) body.shape_ref = shapeRef
      if (shape) body.shape = shape     // explicit figure text (curvy control)
      const { job: jid } = await api.send('/api/bio/body-ref/create', 'POST', body)
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        if (epoch !== switchEpoch.current) return   // switched away — don't leak into the other profile
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
        setBodyCreating(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(st.error); else setBodyPreview(st.run); break }
      }
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setBodyCreating(null) }
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
  const deleteWardrobe = async (item) => {
    if (!window.confirm(`Delete outfit "${item.id}"? This can't be undone.`)) return
    try {
      await fetch(`/api/wardrobe/${item.file}`, { method: 'DELETE' })
      if (outfit === item.id) setOutfit('')
      await refresh()
    } catch (e) { setErr(String(e)) }
  }
  const deleteRun = async (run) => {
    if (!window.confirm('Delete this image? This removes it permanently.')) return
    try {
      await fetch(`/api/runs/${run.id}`, { method: 'DELETE' })
      setDetail((d) => (d && d.id === run.id ? null : d))
      await refresh()
    } catch (e) { setErr(String(e)) }
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
    const epoch = switchEpoch.current
    setErr(null)
    try { return await api.send('/api/video-direct', 'POST', { scenario }) }
    catch (e) { if (epoch === switchEpoch.current) setErr(String(e)); throw e }
  }
  // Phase 3: generate the scene still (brief + matched wardrobe) to animate.
  const generateSceneStill = async ({ brief, wardrobe }) => {
    const epoch = switchEpoch.current
    setErr(null)
    const { job: jid } = await api.send('/api/shot', 'POST', {
      brief, wardrobe_id: wardrobe || null, aspect: '9:16', resolution: '2K',
    })
    for (;;) {
      await new Promise((r) => setTimeout(r, 1800))
      if (epoch !== switchEpoch.current) throw new Error('cancelled — switched character')
      const st = await api.get(`/api/jobs/${jid}`)
      if (st.done) {
        if (st.error) throw new Error(String(st.error))
        if (epoch !== switchEpoch.current) throw new Error('cancelled — switched character')
        await refresh()
        return st.run   // { id, file, verdict, ... }
      }
    }
  }
  const makeVideo = async (payload) => {
    const epoch = switchEpoch.current
    setMakeBusy('starting…'); setErr(null)
    try {
      const { job: jid } = await api.send('/api/make-video', 'POST', payload)
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000))
        if (epoch !== switchEpoch.current) return
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
        setMakeBusy(st.stage || 'working…')
        if (st.done) { if (st.error) setErr(String(st.error)); break }
      }
      if (epoch === switchEpoch.current) await refresh()
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setMakeBusy(null) }
  }
  const animate = async (payload) => {
    const epoch = switchEpoch.current
    setVideoBusy('starting…'); setErr(null)
    try {
      const { job: jid } = await api.send('/api/animate', 'POST', payload)
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000))
        if (epoch !== switchEpoch.current) return
        const st = await api.get(`/api/jobs/${jid}`)
        if (epoch !== switchEpoch.current) return
        setVideoBusy(STAGE[st.stage] || st.stage || 'generating…')
        if (st.done) { if (st.error) setErr(String(st.error)); break }
      }
      if (epoch === switchEpoch.current) await refresh()
    } catch (e) { if (epoch === switchEpoch.current) setErr(String(e)) }
    finally { if (epoch === switchEpoch.current) setVideoBusy(null) }
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

  if (view === 'landing') {
    return (
      <>
        <Landing characters={characters} active={activeChar?.id}
          onSelect={enterCharacter} onCreate={createCharacter} onDelete={deleteCharacter} />
        {err && (
          <div onClick={() => setErr(null)}
            className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 cursor-pointer rounded-md border border-[#5d2926] bg-[#211313] px-4 py-2 text-xs text-[#f18b84]">
            {err} <span className="text-[#9b6764]">· dismiss</span>
          </div>
        )}
      </>
    )
  }

  return (
    <div className="min-h-screen bg-[#0c0c0f] text-[#e6e6ea]">
      <Header tab={tab} setTab={setTab} gallery={gallery}
        character={activeChar} onSwitchCharacter={backToLanding}
        count={runs.filter((r) => !r.meta?.outfit_create && !r.meta?.body_ref_create && !r.meta?.calibrate).length} />

      {loading && (
        <div className="fixed inset-0 top-16 z-30 flex flex-col items-center justify-center gap-3 bg-[#0c0c0f]/85 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-sm text-[#9fd0ff]">
            <LoaderCircle className="h-5 w-5 animate-spin" />
            {buildStage || `Loading ${activeChar?.name || 'character'}…`}
          </div>
          {buildStage && <p className="text-xs text-[#767684]">Creating {activeChar?.name} — this takes a minute.</p>}
        </div>
      )}

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
          faceAcc={faceAcc} setFaceAcc={setFaceAcc}
          wardrobe={wardrobe} poseRefs={poseRefs}
          outfitText={outfitText} setOutfitText={setOutfitText}
          describing={describing} onDescribe={describe} creating={creating} onCreateOutfit={createOutfit}
          outfitPreview={outfitPreview} onSaveOutfit={saveOutfit} onDiscardOutfit={discardOutfit}
          saveCategory={saveCategory} setSaveCategory={setSaveCategory}
          onOpenDesigner={openDesigner}
          onUploadOutfit={uploadTo('/api/wardrobe/upload')} onUploadPose={uploadTo('/api/pose-refs/upload')}
          onDeleteWardrobe={deleteWardrobe} stamp={stamp}
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
          onCreateBody={createBodyRef} onUploadShape={uploadShape}
          onSaveBody={saveBodyRef} onDiscardBody={discardBodyRef}
        />
      )}

      {tab === 'calibrate' && (
        <Calibrate bio={bio} gallery={gallery} stamp={stamp} onRefresh={refresh}
          cands={calibCands} onGenerate={generateCalibFaces} onToggle={toggleCalib}
          onAddSelected={addCalibToGallery} onSetIdentity={setCalibIdentity}
          onEditBio={() => setTab('bio')}
          onUploadBase={async (e) => {
            const f = e.target.files?.[0]; e.target.value = ''
            if (!f) return
            try {
              const info = await api.upload('/api/refs/upload', f)
              if (!info.usable) { setErr('No face detected in that image — pick a clear face photo.'); return }
              // Set it as the calibration SEED, NOT the default BIO identity.
              // The BIO identity is set only by promoting a generated face (⭐).
              await api.send('/api/calibrate/seed', 'POST', { reference: info.name })
              await refresh()
            } catch (er) { setErr(String(er)) }
          }} />
      )}

      {tab === 'video' && <VideoStudio runs={runs} cameraMoves={cameraMoves.moves} models={cameraMoves.models} videos={videos} wardrobe={wardrobe} onAnimate={animate} onDirect={videoDirect} onGenerateStill={generateSceneStill} onMakeVideo={makeVideo} busy={videoBusy} makeBusy={makeBusy} stamp={stamp} />}

      {tab === 'review' && <Review runs={runs} onOpen={setDetail} onMark={mark} onDelete={deleteRun} stats={stats} onExportGold={exportGold} onPurgeRejected={purgeRejected} />}

      <OutfitDrawer open={drawerOpen} imageUrl={outfitImageUrl} describing={describing}
        outfitText={outfitText} setOutfitText={setOutfitText} details={details} onDetail={setDetailField}
        idea={idea} setIdea={setIdea} pickers={pickers} onPicker={setPicker}
        enriching={enriching} onEnrich={enrichOutfit} onDescribe={describe}
        creating={creating} onClose={() => setDrawerOpen(false)}
        onGenerate={() => { setDrawerOpen(false); createOutfit() }} />

      <OriginModal run={detail} wardrobe={wardrobe} poseRefs={poseRefs} stamp={stamp}
        onClose={() => setDetail(null)} onMark={mark} onToWardrobe={toWardrobe} onToPoseRef={toPoseRef} />
    </div>
  )
}
