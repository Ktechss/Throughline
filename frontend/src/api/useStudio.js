import { useCallback, useEffect, useRef, useState } from "react";
import { confirm } from "@/components/ui/confirm";
import { toast } from "@/components/ui/use-toast";
import { api, jobStream, awaitJob, setApiCharacter, apiCharacter, genView, groupPoses, outfitView, nailView, runView, ep, mergeOutfit, STAGE } from "@/api/throughline";

// The studio orchestration hub — ported from the legacy App.jsx. Loads all of the
// active character's data and exposes every action the tabs call. Polling is
// epoch-guarded so a character switch cancels in-flight jobs cleanly.
export function useStudio(charParam) {
  const epoch = useRef(0);
  // Every open job stream, so unmounting actually closes them. The old poll
  // loops had no cleanup at all: `epoch` only moves on a CHARACTER SWITCH
  // (inside load()), so navigating away from the Studio left every loop
  // running against a dead component until the tab was closed.
  const watchers = useRef(new Set());
  useEffect(() => () => {
    watchers.current.forEach((stop) => { try { stop(); } catch { /* already shut */ } });
    watchers.current.clear();
  }, []);
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
  const [aspect, setAspect] = useState("3:4");
  // THE CAPTURE AXES. All four existed server-side and none of them were sent
  // from this tab: measured over the first 607 runs, `flaws` was set 0 times and
  // `camera_holder` 7. Left blank they are now INFERRED from the brief, so ""
  // means "let the brief decide", not "off".
  const [holder, setHolder] = useState("");
  const [flaws, setFlaws] = useState("");
  const [optics, setOptics] = useState("");
  const [exposure, setExposure] = useState("");
  const [groomingState, setGroomingState] = useState("");
  const [clutter, setClutter] = useState("");
  const [shotLib, setShotLib] = useState(null);
  // THE THREE OPT-INS. Each was made deliberately per-request by a commit that
  // argued the case well, and then given nothing to opt in with — so all three
  // sat at their default across the first 613 runs.
  const [safety, setSafety] = useState("");       // fal moderation dial, 1-6
  const [refBudget, setRefBudget] = useState(false);
  const [useTimeline, setUseTimeline] = useState(false);
  const [shotDate, setShotDate] = useState("");   // ISO; blank = today
  const [faceAcc, setFaceAcc] = useState(true);
  const [pov, setPov] = useState(false);   // faceless first-person POV product/lifestyle shot
  // Attach her pinned body reference as a THIRD image, even when an outfit
  // already owns @image2. Off by default because a third reference is
  // measured to cost ~0.04 identity — on when the figure matters more.
  //
  // It exists because a wardrobe turnaround compresses her build: four
  // full-body panels across one canvas leaves each figure a few hundred
  // pixels tall, and bust volume does not survive that. Every saved outfit
  // came back slimmer than the body it was generated from. This bypasses the
  // swatch and asserts the body directly.
  const [bodyRef, setBodyRef] = useState(false);
  // Which model renders. null follows the project default (/api/models), so a
  // shot and the wardrobe it wears can be made on different renderers without
  // either one changing the default for everything else.
  const [model, setModel] = useState(null);
  const [outfitModel, setOutfitModel] = useState(null);
  // A COLLABORATION: the other character whose face rides as @image2.
  const [withChar, setWithChar] = useState(null);
  const [castable, setCastable] = useState([]);   // others who have a master face
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

  // video — the catalogue is per-install, not per-character, so it is fetched
  // once rather than on every character switch.
  const [videoCat, setVideoCat] = useState(null);
  const [animating, setAnimating] = useState({});   // { runId: stage label }

  // calibrate + body previews
  const [calibCands, setCalibCands] = useState([]);
  const [bodyPreview, setBodyPreview] = useState(null);
  const [bodyBusy, setBodyBusy] = useState(null);

  const fail = (e) => setErr(String(e));

  // EACH ANSWER LANDS AS IT ARRIVES.
  //
  // This was one Promise.all over twelve requests, applying no state until the
  // slowest resolved — and /api/refs ran ArcFace over every reference, taking
  // ten seconds. So marking a shot fired the write, fetched the new runs in
  // 200ms, and then sat on them for another ten seconds waiting for an endpoint
  // the Review tab does not even read. The mark HAD worked; the UI just would
  // not say so, which is indistinguishable from a broken button.
  //
  // Requests still go out together — this is not slower — but a slow one now
  // delays only its own slice of the page.
  const refresh = useCallback(async () => {
    const mine = epoch.current;
    const fresh = () => mine === epoch.current;
    const put = (url, apply) =>
      api.get(url).then((d) => { if (fresh()) apply(d); }).catch(() => {});

    const all = [
      put("/api/runs", (r) => setRuns(r.runs)),
      put("/api/stats", setStats),
      put("/api/gallery", setGallery),
      put("/api/parts", (p) => setParts(p.parts)),
      put("/api/refs", (rf) => setRefs(rf.refs)),
      put("/api/wardrobe", (wd) => setWardrobe((wd.wardrobe || []).map(outfitView))),
      put("/api/pose-library", (pl) => setPoseGroups(groupPoses(pl.poses, pl.categories))),
      // /api/pose-refs was fetched here on every refresh and the response
      // thrown away — there is no poseRefs state and nothing reads it. One
      // fewer request per mark, per generation, per tab switch.
      put("/api/bodies", setBodies),
      put("/api/nails", (nl) => setNails((nl.nails || []).map(nailView))),
      put("/api/home", (pc) => setHome(pc || { style: "", corners: [] })),
      put("/api/bio", (b) => {
        setBio(b);
        // Restore the most recent body candidate from the ledger. It used to
        // live only here in page state, so switching tabs or reloading threw
        // away a body you had just generated — the run was always on disk,
        // nothing was showing it. Only restore when nothing is in flight, so a
        // refresh mid-generation cannot yank a newer preview out from under you.
        setBodyPreview((cur) => cur || (b.body_candidates?.[0]
          ? { id: b.body_candidates[0].run_id, file: b.body_candidates[0].file }
          : null));
      }),
    ];
    // Callers that await refresh() still get "everything has landed".
    await Promise.all(all);
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    epoch.current += 1;
    const mine = epoch.current;
    try {
      const chars = await api.get("/api/characters");
      const id = charParam || chars.active;
      // Every subsequent call names this character explicitly, so nothing that
      // moves the server's default can redirect this tab's work.
      setApiCharacter(id);
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
      setWithChar(null);
      // Anyone else with a master face can be shot with. has_reference is the
      // same flag the roster gates entry on — a character without one cannot be
      // photographed at all, alone or otherwise.
      setCastable((chars.characters || []).filter((c) => c.id !== id && c.has_reference)
                                          .map((c) => ({ id: c.id, name: c.name })));
      await refresh();
      // Restore existing calibration candidates for this character so they survive
      // a page reload / character switch (they live on the backend; the UI used to
      // show only the ones generated live in the current session).
      try {
        const cc = await api.get("/api/calibrate/candidates");
        if (mine !== epoch.current) return;
        const items = (cc.candidates || []).map((c) => ({
          jid: c.id, id: c.id, angle: c.angle, url: `/api/images/${c.file}`,
          // `kind` separates calibration angles from MASTER-FACE candidates, and
          // `file` is what the thumbnail endpoint keys on — the studio's
          // no-face gate needs both.
          kind: c.kind, file: c.file,
          running: false, sel: false,
          yaw: c.verdict?.yaw, facePx: c.verdict?.face_px,
        }));
        if (items.length) setCalibCands(items);
      } catch { /* no candidates yet — fine */ }
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setLoading(false); }
  }, [charParam, refresh]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/api/video/models").then(setVideoCat).catch(() => {}); }, []);
  useEffect(() => { api.get("/api/shot/options").then(setShotLib).catch(() => {}); }, []);

  // ------------------------------------------------------------------ shoot
  // SSE, not a poll loop. The old version swallowed every error and
  // rescheduled unconditionally, so after a backend restart the job id 404s
  // forever and the card span at 1.5s until the tab was closed. Now a dead job
  // is a terminal state the card can show.
  const pollGen = (jid) => {
    const mine = epoch.current;
    const stop = jobStream(jid, {
      onStage: (st) => {
        if (mine !== epoch.current) return stop();
        setGenerations((gs) => gs.map((g) => (g.jid === jid
          ? { ...g, status: st, run: st.run || g.run } : g)));
      },
      onDone: (run, st) => {
        if (mine !== epoch.current) return;
        setGenerations((gs) => gs.map((g) => (g.jid === jid
          ? { ...g, status: st, run: run || g.run } : g)));
        refresh().catch(() => {});
      },
      onError: (msg) => {
        if (mine !== epoch.current) return;
        setGenerations((gs) => gs.map((g) => (g.jid === jid
          ? { ...g, status: { ...(g.status || {}), done: true, error: msg } } : g)));
      },
    });
    watchers.current.add(stop);
    return stop;
  };

  // What the shot will actually send, built from the SAME body as onGenerate.
  //
  // Not a second description of the request: the two share `shotBody` here and
  // the server composes the preview by running shot() with preview=true, so the
  // string shown is the string sent. The previous preview composed its own
  // approximation and reported 880 characters for a prompt that shipped 4,517 —
  // it was reassuring precisely when it should have warned.
  const shotBody = () => ({
    brief, aspect, prompt: pov ? null : (aiPrompt.trim() || null),
    wardrobe_id: selectedOutfit?.id || null, pose_ref_id: null,
    pose_id: selectedPose?.id || null, pose_text: null,
    nail_id: selectedNail?.id || null,
    resolution, face_accessories: faceAcc, body_ref: bodyRef,
    pov, shot_type: pov ? "pov" : "candid",
    camera_holder: holder, flaws, optics, exposure,
    grooming_state: groomingState, clutter,
    safety_tolerance: safety || null,
    ref_budget: refBudget,
    use_timeline: useTimeline,
    date: shotDate || null,
    with_character: withChar?.id || null,
    model,
  });

  const [shotPreview, setShotPreview] = useState(null);
  useEffect(() => {
    if (!bio?.reference || (!brief && !selectedOutfit && !selectedPose)) {
      setShotPreview(null); return;
    }
    const t = setTimeout(() => {
      api.send("/api/shot/preview", "POST", shotBody())
         .then(setShotPreview).catch(() => setShotPreview(null));
    }, 350);
    return () => clearTimeout(t);
    // Deps are the fields shotBody() reads, listed explicitly — shotBody itself
    // is recreated every render and would retrigger this on every keystroke.
  }, [brief, aiPrompt, selectedOutfit?.id, selectedPose?.id, selectedNail?.id,
      resolution, aspect, faceAcc, bodyRef, pov, withChar?.id, bio?.reference,
      holder, flaws, optics, exposure, groomingState, clutter,
      safety, refBudget, useTimeline, shotDate]);

  const onGenerate = async () => {
    if (!bio?.reference) { setErr("No identity reference yet — calibrate her first."); return; }
    setErr(null);
    const label = brief.trim().slice(0, 40) || (selectedOutfit ? `outfit: ${selectedOutfit.name}` : "untitled shot");
    const tmp = `tmp-${Date.now()}-${Math.round(Math.random() * 1e6)}`;
    setGenerations((gs) => [{ jid: tmp, label, status: { stage: "starting", elapsed: 0, done: false }, run: null }, ...gs]);
    try {
      const { job } = await api.send("/api/shot", "POST", shotBody());
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
      const { job } = await api.send("/api/wardrobe/create", "POST",
        { outfit: mergeOutfit(outfitText, details), model: outfitModel });
      // awaitJob, not a poll loop: the loop threw on any non-2xx, so ONE
      // dropped request abandoned a job that was still running and still
      // billing. EventSource rides out a blip and only gives up for real.
      const run = await awaitJob(job, (st) =>
        setCreating(STAGE[st.stage] || st.stage || "generating…"));
      if (mine !== epoch.current) return;
      setOutfitPreview(run);
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
      // Was a bare fetch with no X-Character: the upload landed in whichever
      // character was globally active, not the one this tab is showing.
      const r = await fetch("/api/nails/upload", { method: "POST", body: fd,
        headers: apiCharacter() ? { "X-Character": apiCharacter() } : {} });
      if (!r.ok) throw new Error((await r.text()).slice(0, 300));
      const saved = await r.json();
      await refresh();
      setSelectedNail(nailView(saved));
    } catch (e) { fail(e); }
  };
  const deleteNail = async (id) => {
    const item = nails.find((n) => n.id === id);
    if (!item) return;
    try { await api.del(`/api/nails/${item.file}`); if (selectedNail?.id === id) setSelectedNail(null); await refresh(); }
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
      await awaitJob(job, (st) =>
        setHomeBusy((b) => ({ ...b, [key]: STAGE[st.stage] || st.stage || "generating…" })));
      if (mine === epoch.current) await refresh();
    } catch (e) { if (mine === epoch.current) fail(e); }
    finally { if (mine === epoch.current) setHomeBusy((b) => { const n = { ...b }; delete n[key]; return n; }); }
  };
  const deleteCorner = async (key) => {
    try { await api.del(`/api/home/${key}`); await refresh(); }
    catch (e) { fail(e); }
  };

  // ------------------------------------------------------------------ review
  const mark = async (id, decision) => {
    try { await api.send(`/api/runs/${id}/mark`, "POST", { decision }); await refresh(); }
    catch (e) { fail(e); }
  };
  const deleteRun = async (id) => {
    if (!(await confirm({ title: "Delete this image?", body: "The file is removed from disk. This cannot be undone.", danger: true }))) return;
    try { await api.del(`/api/runs/${id}`); await refresh(); }
    catch (e) { fail(e); }
  };
  const exportGold = async () => {
    try { const r = await api.send("/api/gold/export", "POST", {}); await refresh();
      toast.ok("Gold set exported",
        `${r.exported} approved shots → data/gold/ · ${r.gold_on_disk} on disk`); }
    catch (e) { fail(e); }
  };
  const purgeRejected = async () => {
    if (!(await confirm({ title: "Delete every rejected image?", body: "They are removed from disk. This cannot be undone.", danger: true }))) return;
    try { const r = await api.send("/api/runs/purge-rejected", "POST", {}); await refresh();
      toast.ok(`Deleted ${r.deleted} rejected images`, `freed ${r.freed_mb} MB`); }
    catch (e) { fail(e); }
  };
  const cleanupImages = async () => {
    if (!(await confirm({ title: "Reclaim disk space?", body: "Deletes orphaned images and spent outfit, body and calibration intermediates. Your review shots are kept.", confirmLabel: "Clean up", danger: true }))) return;
    try { const r = await api.send("/api/images/cleanup", "POST", {}); await refresh();
      toast.ok(`Freed ${r.freed_mb} MB`,
        `${r.intermediates} intermediates · ${r.orphans} orphans · ${r.stale_thumbs} stale thumbnails`); }
    catch (e) { fail(e); }
  };

  // ------------------------------------------------------------------ animate
  // Turn an approved still into a clip. The still becomes frame one, so identity
  // is inherited rather than re-argued — which is why the server refuses an
  // ungated source unless allow_ungated says the owner looked and wants it.
  //
  // Polled at 3s, not the 1.5s the still path uses: a clip renders in MINUTES
  // (the server's own budget is an hour), so a faster tick is a hundred wasted
  // round trips per render and no sooner an answer.
  const animate = async (runId, opts = {}) => {
    const mine = epoch.current;
    setAnimating((a) => ({ ...a, [runId]: "starting…" })); setErr(null);
    try {
      const { job } = await api.send("/api/video", "POST", { run_id: runId, ...opts });
      // A clip renders in MINUTES and the old 3s poll had the same fatal
      // property as the rest: one blip in ~800 requests reported failure for a
      // render that completed fine, and the user re-rendered it.
      const run = await awaitJob(job, (st) =>
        setAnimating((a) => ({ ...a, [runId]: STAGE[st.stage] || st.stage || "rendering…" })));
      if (mine !== epoch.current) return null;
      await refresh();
      return run;
    } catch (e) {
      if (mine === epoch.current) fail(e);
      return null;
    } finally {
      if (mine === epoch.current) setAnimating((a) => { const n = { ...a }; delete n[runId]; return n; });
    }
  };

  // Ask Claude what should move in a shot. Costs one vision call and renders
  // nothing — the owner picks a suggestion and presses animate themselves.
  const suggestMotion = async (runId, opts = {}) => {
    try {
      return await api.send("/api/video/suggest", "POST", { run_id: runId, ...opts });
    } catch (e) {
      fail(e);
      return null;
    }
  };

  // ------------------------------------------------- bulk + CRUD (multi-select)
  const bulkDeleteRuns = async (ids) => {
    if (!ids.length || !(await confirm({ title: `Delete ${ids.length} image${ids.length > 1 ? "s" : ""}?`, body: "The files are removed from disk. This cannot be undone.", danger: true }))) return;
    try { await api.send("/api/runs/delete", "POST", { ids }); await refresh(); } catch (e) { fail(e); }
  };
  const bulkMarkRuns = async (ids, decision) => {
    if (!ids.length) return;
    try { await api.send("/api/runs/mark-bulk", "POST", { ids, decision }); await refresh(); } catch (e) { fail(e); }
  };
  const deleteOutfit = async (id) => {
    if (!(await confirm({ title: "Delete this outfit?", danger: true }))) return;
    try { await api.del(`/api/wardrobe/${id}`); await refresh(); } catch (e) { fail(e); }
  };
  const updateOutfit = async (id, patch) => {
    try { await api.send(`/api/wardrobe/${id}`, "PUT", patch); await refresh(); } catch (e) { fail(e); }
  };
  const bulkDeleteOutfits = async (ids) => {
    if (!ids.length || !(await confirm({ title: `Delete ${ids.length} outfit${ids.length > 1 ? "s" : ""}?`, danger: true }))) return;
    try { for (const id of ids) await api.del(`/api/wardrobe/${id}`); await refresh(); } catch (e) { fail(e); }
  };
  const updateNail = async (id, patch) => {
    try { await api.send(`/api/nails/${id}`, "PUT", patch); await refresh(); } catch (e) { fail(e); }
  };
  const bulkDeleteNails = async (ids) => {
    if (!ids.length || !(await confirm({ title: `Delete ${ids.length} manicure${ids.length > 1 ? "s" : ""}?`, danger: true }))) return;
    const byId = Object.fromEntries((nails || []).map((n) => [n.id, n.file || n.id]));
    try { for (const id of ids) await api.del(`/api/nails/${byId[id] || id}`); await refresh(); } catch (e) { fail(e); }
  };
  const bulkDeleteRefs = async (names) => {
    if (!names.length || !(await confirm({ title: `Delete ${names.length} reference${names.length > 1 ? "s" : ""}?`, body: "References are how identity is carried — a face cannot be described back.", danger: true }))) return;
    try { for (const n of names) await api.del(`/api/refs/${n}`); await refresh(); } catch (e) { fail(e); }
  };
  const removeGalleryEntry = async (name) => {
    if (!(await confirm({ title: `Remove "${name}" from the gallery?`, body: "The threshold re-derives from what is left, so every later verdict shifts with it.", confirmLabel: "Remove", danger: true }))) return;
    try { await api.send("/api/gallery/remove", "POST", { name }); await refresh(); } catch (e) { fail(e); }
  };
  const renameBody = async (id, name) => {
    if (!name || !name.trim()) return;
    try { await api.send(`/api/bodies/${id}`, "PUT", { name: name.trim() }); await refresh(); } catch (e) { fail(e); }
  };

  // ------------------------------------------------------------------ bio
  const setBioRef = async (name) => { try { await api.send("/api/bio/reference", "PUT", { reference: name }); await refresh(); } catch (e) { fail(e); } };
  const deleteRef = async (name) => { try { await api.del(`/api/refs/${name}`); await refresh(); } catch (e) { fail(e); } };
  const toGallery = async (name, view) => { try { await api.send("/api/gallery/from-ref", "POST", { name, view }); await refresh(); } catch (e) { fail(e); } };
  const importRef = async (path) => { try { await api.send("/api/refs/import", "POST", { path }); await refresh(); } catch (e) { fail(e); } };
  const uploadRef = async (file) => { try { await api.upload("/api/refs/upload", file); await refresh(); } catch (e) { fail(e); } };
  const savePart = async (id, patch) => {
    const next = parts.map((p) => (p.id === id ? { ...p, ...patch } : p));
    setParts(next);
    try { await api.send("/api/parts", "PUT", { parts: next }); } catch (e) { fail(e); }
  };
  const resetParts = async () => {
    if (!(await confirm({ title: "Reset every part to defaults?", body: "Your edits to her part tree are lost — that tree is her written identity, not settings.", confirmLabel: "Reset", danger: true }))) return;
    try { const r = await api.send("/api/parts/reset", "POST", {}); setParts(r.parts); } catch (e) { fail(e); }
  };

  // bodies
  const uploadShape = async (file) => { try { return await api.upload("/api/bio/shape-ref/upload", file); } catch (e) { fail(e); } };
  const createBody = async (shapeRef, shape) => {
    const mine = epoch.current;
    setBodyBusy("starting…"); setErr(null); setBodyPreview(null);
    try {
      const body = { model }; if (shapeRef) body.shape_ref = shapeRef; if (shape) body.shape = shape;
      const { job } = await api.send("/api/bio/body-ref/create", "POST", body);
      const run = await awaitJob(job, (st) => setBodyBusy(st.stage || "generating…"));
      if (mine !== epoch.current) return;
      setBodyPreview(run);
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
  // Tell the server too, or the next refresh restores it from the ledger and
  // asks you to save-or-discard the same body again.
  const discardBody = async () => {
    const id = bodyPreview?.id;
    setBodyPreview(null);
    if (id) { try { await api.send("/api/bio/body-ref/dismiss", "POST", { run_id: id }); } catch { /* local clear is enough */ } }
  };
  const selectBody = async (id) => { try { await api.send("/api/bodies/select", "POST", { id }); await refresh(); } catch (e) { fail(e); } };
  const deleteBody = async (id) => { try { await api.del(`/api/bodies/${id}`); await refresh(); } catch (e) { fail(e); } };

  // ------------------------------------------------------------------ calibrate
  const pollCalib = (jid) => {
    const mine = epoch.current;
    const settle = (patch) => {
      if (mine !== epoch.current) return;
      setCalibCands((cs) => cs.map((c) => (c.jid === jid ? { ...c, ...patch } : c)));
    };
    const stop = jobStream(jid, {
      onStage: (st) => (mine === epoch.current ? settle({ stage: st.stage }) : stop()),
      onDone: (run) => settle({
        running: false, id: run.id, url: `/api/images/${run.file}`,
        yaw: run.verdict?.yaw, facePx: run.verdict?.face_px,
      }),
      onError: (msg) => settle({ running: false, error: String(msg).slice(0, 100) }),
    });
    watchers.current.add(stop);
    return stop;
  };
  const generateFaces = async (count) => {
    setErr(null);
    try {
      const { jobs } = await api.send("/api/calibrate/faces", "POST", { count, model });
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
    if (!(await confirm({ title: "Wipe the identity fingerprint?", body: "The gallery and threshold are cleared, so every run comes back ungated until you calibrate again.", confirmLabel: "Wipe", danger: true }))) return;
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
    aspect, setAspect, shotLib,
    holder, setHolder, flaws, setFlaws, optics, setOptics,
    exposure, setExposure, groomingState, setGroomingState,
    clutter, setClutter,
    safety, setSafety, refBudget, setRefBudget,
    useTimeline, setUseTimeline, shotDate, setShotDate,
    faceAcc, setFaceAcc, pov, setPov, selectedOutfit, setSelectedOutfit, selectedPose, setSelectedPose,
    selectedNail, setSelectedNail, nails, saveNail, deleteNail, updateNail, bulkDeleteNails,
    home, homeBusy, saveHome, uploadCorner, generateCorner, deleteCorner,
    gens, onGenerate, shotPreview, bodyRef, setBodyRef,
    model, setModel, outfitModel, setOutfitModel,
    // outfit designer
    drawerOpen, openDesigner, closeDesigner, outfitText, setOutfitText, outfitImageUrl,
    details, setDetailField, idea, setIdea, pickers, setPicker, describing, enriching, creating,
    outfitPreview, describeOutfit, enrichOutfit, createOutfit, saveOutfit, discardOutfit, uploadOutfit,
    outfitCategories, deleteOutfit, updateOutfit, bulkDeleteOutfits,
    // review
    shots, mark, deleteRun, exportGold, purgeRejected, cleanupImages, bulkDeleteRuns, bulkMarkRuns,
    // video
    videoCat, animating, animate, suggestMotion,
    // bio
    setBioRef, deleteRef, toGallery, importRef, uploadRef, savePart, resetParts, bulkDeleteRefs,
    uploadShape, createBody, saveBody, discardBody, selectBody, deleteBody, renameBody, bodyPreview, bodyBusy,
    // calibrate
    withChar, setWithChar, castable,
    calibCands, generateFaces, toggleCalib, addCalibToGallery, setCalibIdentity, recalibrate, resetGallery, uploadSeed, removeGalleryEntry,
    ep,
  };
}
