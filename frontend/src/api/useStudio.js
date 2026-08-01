import { useCallback, useEffect, useRef, useState } from "react";
import { api, genView, groupPoses, outfitView, nailView, runView, ep, mergeOutfit, STAGE } from "@/api/throughline";

// The studio orchestration hub — ported from the legacy App.jsx. Loads all of the
// active character's data and exposes every action the tabs call. Polling is
// epoch-guarded so a character switch cancels in-flight jobs cleanly.
export function useStudio(charParam) {
  const epoch = useRef(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  // character + data
  const [charName, setCharName] = useState("");
  const [hasIdentity, setHasIdentity] = useState(false);
  const [bio, setBio] = useState(null);
  const [gallery, setGallery] = useState({ entries: [], threshold: null });
  const [parts, setParts] = useState([]);
  const [refs, setRefs] = useState([]);
  const [bodies, setBodies] = useState({ bodies: [], active: null });
  const [wardrobe, setWardrobe] = useState([]);
  const [poseGroups, setPoseGroups] = useState({});
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState(null);

  // shoot
  const [brief, setBrief] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [resolution, setResolution] = useState("4K");
  const [faceAcc, setFaceAcc] = useState(true);
  const [pov, setPov] = useState(false);   // faceless first-person POV product/lifestyle shot
  const [selectedOutfit, setSelectedOutfit] = useState(null);
  const [selectedPose, setSelectedPose] = useState(null);
  const [selectedNail, setSelectedNail] = useState(null);
  const [nails, setNails] = useState([]);
  const [home, setHome] = useState({ style: "", corners: [] });
  const [homeBusy, setHomeBusy] = useState({});   // { cornerKey: stageLabel } while generating
  const [generations, setGenerations] = useState([]);

  // outfit designer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [outfitText, setOutfitText] = useState("");
  const [outfitImageUrl, setOutfitImageUrl] = useState(null);
  const [details, setDetails] = useState(null);
  const [idea, setIdea] = useState("");
  const [pickers, setPickers] = useState({});
  const [describing, setDescribing] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [creating, setCreating] = useState(null);
  const [outfitPreview, setOutfitPreview] = useState(null);

  // calibrate + body previews
  const [calibCands, setCalibCands] = useState([]);
  const [bodyPreview, setBodyPreview] = useState(null);
  const [bodyBusy, setBodyBusy] = useState(null);

  const fail = (e) => setErr(String(e));

  const refresh = useCallback(async () => {
    const mine = epoch.current;
    const [p, r, g, rf, b, wd, pl, pr, st, bd, nl, pc] = await Promise.all([
      api.get("/api/parts"), api.get("/api/runs"), api.get("/api/gallery"),
      api.get("/api/refs"), api.get("/api/bio"), api.get("/api/wardrobe"),
      api.get("/api/pose-library"), api.get("/api/pose-refs"), api.get("/api/stats"),
      api.get("/api/bodies"), api.get("/api/nails"), api.get("/api/home"),
    ]);
    if (mine !== epoch.current) return;
    setParts(p.parts); setRuns(r.runs); setGallery(g); setRefs(rf.refs);
    setBio(b); setWardrobe((wd.wardrobe || []).map(outfitView));
    setPoseGroups(groupPoses(pl.poses, pl.categories));
    setStats(st); setBodies(bd);
    setNails((nl.nails || []).map(nailView));
    setHome(pc || { style: "", corners: [] });
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    epoch.current += 1;
    const mine = epoch.current;
    try {
      const chars = await api.get("/api/characters");
      const id = charParam || chars.active;
      const entry = (chars.characters || []).find((c) => c.id === id);
      if (charParam && charParam !== chars.active) {
        await api.send("/api/characters/active", "PUT", { id: charParam });
      }
      if (mine !== epoch.current) return;
      setCharName(entry?.name || id || "");
      setHasIdentity(!!entry?.has_identity);
      setGenerations([]);
      setSelectedNail(null); setSelectedOutfit(null); setSelectedPose(null);
      setCalibCands([]);
      await refresh();
      // Restore existing calibration candidates for this character so they survive
      // a page reload / character switch (they live on the backend; the UI used to
      // show only the ones generated live in the current session).
      try {
        const cc = await api.get("/api/calibrate/candidates");
        if (mine !== epoch.current) return;
        const items = (cc.candidates || []).map((c) => ({
          jid: c.id, id: c.id, angle: c.angle, url: `/api/images/${c.file}`,
          running: false, sel: false,
          yaw: c.verdict?.yaw, facePx: c.verdict?.face_px,
        }));
        if (items.length) setCalibCands(items);
      } catch { /* no candidates yet — fine */ }
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setLoading(false); }
  }, [charParam, refresh]);

  useEffect(() => { load(); }, [load]);

  // ------------------------------------------------------------------ shoot
  const pollGen = (jid) => {
    const mine = epoch.current;
    const tick = async () => {
      if (mine !== epoch.current) return;
      try {
        const st = await api.get(`/api/jobs/${jid}`);
        if (mine !== epoch.current) return;
        setGenerations((gs) => gs.map((g) => (g.jid === jid ? { ...g, status: st, run: st.run || g.run } : g)));
        if (st.done) { refresh().catch(() => {}); return; }
      } catch { /* transient */ }
      setTimeout(tick, 1500);
    };
    tick();
  };

  const onGenerate = async () => {
    if (!bio?.reference) { setErr("No identity reference yet — calibrate her first."); return; }
    setErr(null);
    const label = brief.trim().slice(0, 40) || (selectedOutfit ? `outfit: ${selectedOutfit.name}` : "untitled shot");
    const tmp = `tmp-${Date.now()}-${Math.round(Math.random() * 1e6)}`;
    setGenerations((gs) => [{ jid: tmp, label, status: { stage: "starting", elapsed: 0, done: false }, run: null }, ...gs]);
    try {
      const { job } = await api.send("/api/shot", "POST", {
        brief, aspect: "3:4", prompt: pov ? null : (aiPrompt.trim() || null),
        wardrobe_id: selectedOutfit?.id || null, pose_ref_id: null,
        pose_id: selectedPose?.id || null, pose_text: null,
        nail_id: selectedNail?.id || null,
        resolution, face_accessories: faceAcc,
        pov, shot_type: pov ? "pov" : "candid",   // faceless first-person product/lifestyle
      });
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, jid: job } : g)));
      pollGen(job);
    } catch (e) {
      fail(e);
      setGenerations((gs) => gs.map((g) => (g.jid === tmp ? { ...g, status: { done: true, error: String(e) } } : g)));
    }
  };

  const onAiPrompt = async () => {
    const mine = epoch.current;
    setAiBusy(true); setErr(null);
    try {
      const r = await api.send("/api/shot/ai-prompt", "POST", {
        brief, wardrobe_id: selectedOutfit?.id || null, pose_ref_id: null,
        pose_id: selectedPose?.id || null, pose_text: null,
      });
      if (mine === epoch.current) setAiPrompt(r.prompt);
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setAiBusy(false); }
  };

  // ------------------------------------------------------------ outfit designer
  const openDesigner = () => { setDetails(null); setOutfitImageUrl(null); setDrawerOpen(true); };
  const closeDesigner = () => setDrawerOpen(false);
  const setDetailField = (k, v) => setDetails((d) => ({ ...(d || {}), [k]: v }));
  const setPicker = (k, v) => setPickers((p) => ({ ...p, [k]: v }));

  // Upload an outfit photo -> Claude describes it -> fills the designer box.
  const describeOutfit = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    const mine = epoch.current;
    setOutfitImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(f); });
    setDrawerOpen(true); setDescribing(true); setErr(null);
    try {
      const d = await api.upload("/api/wardrobe/describe", f);
      if (mine !== epoch.current) return;
      setOutfitText(d.outfit); setDetails(d.details || {});
    } catch (e2) { if (mine === epoch.current) fail(e2); }
    finally { if (mine === epoch.current) setDescribing(false); }
  };

  const enrichOutfit = async () => {
    const mine = epoch.current;
    setEnriching(true); setErr(null);
    try {
      const r = await api.send("/api/wardrobe/enrich", "POST", { base: outfitText, idea, ...pickers });
      if (mine === epoch.current) setOutfitText(r.outfit);
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setEnriching(false); }
  };

  const createOutfit = async () => {
    const mine = epoch.current;
    setDrawerOpen(false);   // generation state lives in the Shoot panel, not the closable drawer
    setCreating("starting…"); setErr(null); setOutfitPreview(null);
    try {
      const { job } = await api.send("/api/wardrobe/create", "POST", { outfit: mergeOutfit(outfitText, details) });
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        if (mine !== epoch.current) return;
        const st = await api.get(`/api/jobs/${job}`);
        if (mine !== epoch.current) return;
        setCreating(STAGE[st.stage] || st.stage || "generating…");
        if (st.done) { if (st.error) setErr(st.error); else setOutfitPreview(st.run); break; }
      }
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setCreating(null); }
  };

  const saveOutfit = async (category) => {
    const cat = (category || "").trim();
    if (!cat) { setErr("Pick a category before saving."); return; }
    if (!outfitPreview) return;
    try {
      const r = await api.send("/api/wardrobe/from-run", "POST", { run_id: outfitPreview.id, category: cat });
      setOutfitPreview(null); setOutfitText(""); setDetails(null); setDrawerOpen(false);
      await refresh();
      setSelectedOutfit(outfitView({ id: r.id, file: r.file, category: cat }));
    } catch (e) { fail(e); }
  };
  const discardOutfit = () => setOutfitPreview(null);

  const uploadOutfit = async (file) => { try { await api.upload("/api/wardrobe/upload", file); await refresh(); } catch (e) { fail(e); } };

  // ---- nail styles ----
  // Image-only: pick a colour, name is auto <colour><n>. No Claude describe.
  const saveNail = async ({ file, color }) => {
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("color", color || "other");
      const r = await fetch("/api/nails/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.text()).slice(0, 300));
      const saved = await r.json();
      await refresh();
      setSelectedNail(nailView(saved));
    } catch (e) { fail(e); }
  };
  const deleteNail = async (id) => {
    const item = nails.find((n) => n.id === id);
    if (!item) return;
    try { await fetch(`/api/nails/${item.file}`, { method: "DELETE" }); if (selectedNail?.id === id) setSelectedNail(null); await refresh(); }
    catch (e) { fail(e); }
  };

  // ---- home (BIO): shared style + per-corner image (upload or generate) ----
  const saveHome = async (patch) => {
    const next = { style: home.style || "", surroundings: home.surroundings || "", ...patch };
    try { await api.send("/api/home", "PUT", next); setHome((h) => ({ ...h, ...patch })); }
    catch (e) { fail(e); }
  };
  const uploadCorner = async (key, file) => {
    try { await api.upload(`/api/home/${key}/upload`, file); await refresh(); }
    catch (e) { fail(e); }
  };
  const generateCorner = async (key) => {
    const mine = epoch.current;
    setHomeBusy((b) => ({ ...b, [key]: "starting…" })); setErr(null);
    try {
      const { job } = await api.send(`/api/home/${key}/generate`, "POST", {});
      for (;;) {
        await new Promise((r) => setTimeout(r, 1800));
        if (mine !== epoch.current) return;
        const st = await api.get(`/api/jobs/${job}`);
        if (mine !== epoch.current) return;
        setHomeBusy((b) => ({ ...b, [key]: STAGE[st.stage] || st.stage || "generating…" }));
        if (st.done) { if (st.error) setErr(st.error); break; }
      }
      if (mine === epoch.current) await refresh();
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setHomeBusy((b) => { const n = { ...b }; delete n[key]; return n; }); }
  };
  const deleteCorner = async (key) => {
    try { await fetch(`/api/home/${key}`, { method: "DELETE" }); await refresh(); }
    catch (e) { fail(e); }
  };

  // ------------------------------------------------------------------ review
  const mark = async (id, decision) => {
    try { await api.send(`/api/runs/${id}/mark`, "POST", { decision }); await refresh(); }
    catch (e) { fail(e); }
  };
  const deleteRun = async (id) => {
    if (!window.confirm("Delete this image permanently?")) return;
    try { await fetch(`/api/runs/${id}`, { method: "DELETE" }); await refresh(); }
    catch (e) { fail(e); }
  };
  const exportGold = async () => {
    try { const r = await api.send("/api/gold/export", "POST", {}); await refresh();
      window.alert(`Gold set exported: ${r.exported} approved shots → data/gold/ (${r.gold_on_disk} on disk).`); }
    catch (e) { fail(e); }
  };
  const purgeRejected = async () => {
    if (!window.confirm("Delete all rejected images from disk? This cannot be undone.")) return;
    try { const r = await api.send("/api/runs/purge-rejected", "POST", {}); await refresh();
      window.alert(`Deleted ${r.deleted} rejected images · freed ${r.freed_mb} MB.`); }
    catch (e) { fail(e); }
  };
  const cleanupImages = async () => {
    if (!window.confirm("Reclaim disk by deleting orphaned images and spent outfit/body/calibration intermediates? Review shots are kept.")) return;
    try { const r = await api.send("/api/images/cleanup", "POST", {}); await refresh();
      window.alert(`Cleaned up · ${r.intermediates} intermediates · ${r.orphans} orphans · ${r.stale_thumbs} stale thumbnails · freed ${r.freed_mb} MB.`); }
    catch (e) { fail(e); }
  };

  // ------------------------------------------------------------------ bio
  const setBioRef = async (name) => { try { await api.send("/api/bio/reference", "PUT", { reference: name }); await refresh(); } catch (e) { fail(e); } };
  const deleteRef = async (name) => { try { await fetch(`/api/refs/${name}`, { method: "DELETE" }); await refresh(); } catch (e) { fail(e); } };
  const toGallery = async (name, view) => { try { await api.send("/api/gallery/from-ref", "POST", { name, view }); await refresh(); } catch (e) { fail(e); } };
  const importRef = async (path) => { try { await api.send("/api/refs/import", "POST", { path }); await refresh(); } catch (e) { fail(e); } };
  const uploadRef = async (file) => { try { await api.upload("/api/refs/upload", file); await refresh(); } catch (e) { fail(e); } };
  const savePart = async (id, patch) => {
    const next = parts.map((p) => (p.id === id ? { ...p, ...patch } : p));
    setParts(next);
    try { await api.send("/api/parts", "PUT", { parts: next }); } catch (e) { fail(e); }
  };
  const resetParts = async () => {
    if (!window.confirm("Reset every part to defaults? Your edits are lost.")) return;
    try { const r = await api.send("/api/parts/reset", "POST", {}); setParts(r.parts); } catch (e) { fail(e); }
  };

  // bodies
  const uploadShape = async (file) => { try { return await api.upload("/api/bio/shape-ref/upload", file); } catch (e) { fail(e); } };
  const createBody = async (shapeRef, shape) => {
    const mine = epoch.current;
    setBodyBusy("starting…"); setErr(null); setBodyPreview(null);
    try {
      const body = {}; if (shapeRef) body.shape_ref = shapeRef; if (shape) body.shape = shape;
      const { job } = await api.send("/api/bio/body-ref/create", "POST", body);
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        if (mine !== epoch.current) return;
        const st = await api.get(`/api/jobs/${job}`);
        if (mine !== epoch.current) return;
        setBodyBusy(st.stage || "generating…");
        if (st.done) { if (st.error) setErr(st.error); else setBodyPreview(st.run); break; }
      }
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setBodyBusy(null); }
  };
  const saveBody = async (name) => {
    if (!name || !bodyPreview) return;
    try {
      const { id } = await api.send("/api/bodies/save", "POST", { run_id: bodyPreview.id, name });
      await api.send("/api/bodies/select", "POST", { id });
      setBodyPreview(null); await refresh();
    } catch (e) { fail(e); }
  };
  const discardBody = () => setBodyPreview(null);
  const selectBody = async (id) => { try { await api.send("/api/bodies/select", "POST", { id }); await refresh(); } catch (e) { fail(e); } };
  const deleteBody = async (id) => { try { await fetch(`/api/bodies/${id}`, { method: "DELETE" }); await refresh(); } catch (e) { fail(e); } };

  // ------------------------------------------------------------------ calibrate
  const pollCalib = (jid) => {
    const mine = epoch.current;
    const tick = async () => {
      if (mine !== epoch.current) return;
      try {
        const st = await api.get(`/api/jobs/${jid}`);
        if (mine !== epoch.current) return;
        if (st.done) {
          setCalibCands((cs) => cs.map((c) => (c.jid === jid
            ? (st.error ? { ...c, running: false, error: String(st.error).slice(0, 100) }
              : { ...c, running: false, id: st.run.id, url: `/api/images/${st.run.file}`, yaw: st.run.verdict?.yaw, facePx: st.run.verdict?.face_px })
            : c)));
          return;
        }
        setCalibCands((cs) => cs.map((c) => (c.jid === jid ? { ...c, stage: st.stage } : c)));
      } catch { /* transient */ }
      setTimeout(tick, 2000);
    };
    tick();
  };
  const generateFaces = async (count) => {
    setErr(null);
    try {
      const { jobs } = await api.send("/api/calibrate/faces", "POST", { count });
      setCalibCands((cs) => [...jobs.map((j) => ({ jid: j.job, angle: j.angle, running: true, sel: false })), ...cs]);
      jobs.forEach((j) => pollCalib(j.job));
    } catch (e) { fail(e); }
  };
  const toggleCalib = (jid) => setCalibCands((cs) => cs.map((c) => (c.jid === jid ? { ...c, sel: !c.sel } : c)));
  const addCalibToGallery = async () => {
    const sel = calibCands.filter((c) => c.sel && c.id);
    if (!sel.length) { setErr("Select at least one on-model face first."); return; }
    try { for (const c of sel) await api.send("/api/calibrate/gallery/add", "POST", { run_id: c.id, view: c.angle }); await refresh(); }
    catch (e) { fail(e); }
  };
  const setCalibIdentity = async (runId) => {
    try { await api.send("/api/bio/reference/from-run", "POST", { run_id: runId, name: "identity" }); await refresh(); setHasIdentity(true); }
    catch (e) { fail(e); }
  };
  const recalibrate = async () => { try { return await api.send("/api/calibrate/recalibrate", "POST", {}); } catch (e) { fail(e); } };
  const resetGallery = async () => {
    if (!window.confirm("Wipe the fingerprint to start a fresh calibration?")) return;
    try { await api.send("/api/calibrate/reset", "POST", {}); await refresh(); } catch (e) { fail(e); }
  };
  const uploadSeed = async (file) => {
    try {
      const info = await api.upload("/api/refs/upload", file);
      if (!info.usable) { setErr("No face detected in that image — pick a clear face photo."); return; }
      await api.send("/api/calibrate/seed", "POST", { reference: info.name });
      await refresh();
    } catch (e) { fail(e); }
  };


  // ---- derived views ----
  const gens = generations.map(genView);
  // /api/runs is already newest-first — keep that order (latest generation first).
  const shots = (runs || []).filter((r) => { const m = r.meta || {}; return !m.outfit_create && !m.body_ref_create && !m.calibrate; })
    .map((r) => ({ ...runView(r), approved: r.mark === "approve", rejected: r.mark === "reject" }));
  const outfitCategories = [...new Set((wardrobe || []).map((w) => w.category).filter((c) => c && c !== "Uncategorized"))];

  return {
    loading, err, setErr, charName, hasIdentity, bio, gallery, parts, refs, bodies, wardrobe,
    poseGroups, stats, refresh,
    // shoot
    brief, setBrief, aiPrompt, setAiPrompt, aiBusy, onAiPrompt, resolution, setResolution,
    faceAcc, setFaceAcc, pov, setPov, selectedOutfit, setSelectedOutfit, selectedPose, setSelectedPose,
    selectedNail, setSelectedNail, nails, saveNail, deleteNail,
    home, homeBusy, saveHome, uploadCorner, generateCorner, deleteCorner,
    gens, onGenerate,
    // outfit designer
    drawerOpen, openDesigner, closeDesigner, outfitText, setOutfitText, outfitImageUrl,
    details, setDetailField, idea, setIdea, pickers, setPicker, describing, enriching, creating,
    outfitPreview, describeOutfit, enrichOutfit, createOutfit, saveOutfit, discardOutfit, uploadOutfit,
    outfitCategories,
    // review
    shots, mark, deleteRun, exportGold, purgeRejected, cleanupImages,
    // bio
    setBioRef, deleteRef, toGallery, importRef, uploadRef, savePart, resetParts,
    uploadShape, createBody, saveBody, discardBody, selectBody, deleteBody, bodyPreview, bodyBusy,
    // calibrate
    calibCands, generateFaces, toggleCalib, addCalibToGallery, setCalibIdentity, recalibrate, resetGallery, uploadSeed,
    ep,
  };
}
