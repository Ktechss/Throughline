import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, charView, STAGE } from "@/api/throughline";
import { ShieldCheck, ShieldAlert, Plus, X, Sparkles, Upload, Ruler, Trash2, Loader2, Pencil, Home } from "lucide-react";
import { cn } from "@/lib/utils";
import FacePicker from "@/components/studio/FacePicker";

const FACE_SHAPES = ["oval", "round", "square", "heart", "diamond", "oblong"];
const BODY_TYPES = ["slim", "athletic", "curvy", "voluptuous", "full-figured"];
// HOME_CORNERS in backend/main.py. Shown so the generation cost of filling in the
// home field is visible before it is paid, not after.
const HOME_CORNER_COUNT = 10;

export default function Landing() {
  const navigate = useNavigate();
  const [characters, setCharacters] = useState([]);
  const [active, setActive] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [building, setBuilding] = useState(null); // progress label while a new character builds
  const [picking, setPicking] = useState(null);   // {character, candidates} awaiting a face choice
  const [err, setErr] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/api/characters");
      setCharacters((r.characters || []).map(charView));
      setActive(r.active);
    } catch (e) { setErr(String(e)); }
  };
  useEffect(() => { load(); }, []);

  // Enter a studio — but only if she HAS a face. A character with no master
  // reference cannot be photographed (shot() refuses), so letting anyone in
  // would hand them a studio where nothing works. If candidates are waiting,
  // the choice is offered here instead; the studio gates on the same condition
  // for anyone arriving by URL.
  const enter = async (c) => {
    const id = typeof c === "string" ? c : c.id;
    // Still building: there is nothing to enter yet and nothing to choose from.
    // Say so instead of opening a studio where every action fails.
    if (c?.status === "building") {
      setErr(`${c.name} is still being built — ${c.job?.stage || "generating"}.`);
      return;
    }
    try { await api.send("/api/characters/active", "PUT", { id }); } catch { /* studio re-sets it too */ }
    if (typeof c === "object" && c && !c.has_reference) {
      try {
        const r = await api.get("/api/calibrate/candidates");
        const cands = (r.candidates || []).filter((x) => x.kind === "master");
        if (cands.length) { setPicking({ character: c, candidates: cands }); return; }
      } catch { /* fall through — better a studio than a dead click */ }
    }
    navigate(`/studio?char=${id}`);
  };

  const remove = async (e, c) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${c.name}" and all of her images, wardrobe and generations? This cannot be undone.`)) return;
    try { await api.send(`/api/characters/${c.id}`, "DELETE"); await load(); }
    catch (er) { setErr(String(er)); }
  };
  const rename = async (e, c) => {
    e.stopPropagation(); e.preventDefault();
    const name = window.prompt("Rename character", c.name);
    if (!name || !name.trim() || name.trim() === c.name) return;
    try { await api.send(`/api/characters/${c.id}`, "PUT", { name: name.trim() }); await load(); }
    catch (er) { setErr(String(er)); }
  };

  // Creation is a DRAFT, not a modal you sit through. Submitting starts a build
  // that takes minutes and then returns immediately: the character row already
  // exists, so she appears in the roster as a card that fills itself in while
  // you carry on working on someone else. The poll below just keeps the cards
  // honest; nothing depends on this tab staying open, and the backend stores the
  // job id on the character so a reload finds it again.
  const create = async (form) => {
    setErr(null);
    setBuilding("Starting…");
    try {
      const fd = new FormData();
      fd.append("name", form.name);
      fd.append("description", form.description || "");
      fd.append("face_shape", form.face_shape || "");
      fd.append("build", form.build || "");
      fd.append("height_cm", form.height_cm || "");
      fd.append("home_style", form.home_style || "");
      fd.append("home_surroundings", form.home_surroundings || "");
      fd.append("reference_mode", form.file ? "inspiration" : "none");
      if (form.file) fd.append("reference", form.file);
      const r = await fetch("/api/characters/guided", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.text()).slice(0, 300));
      await r.json();
      setShowCreate(false);      // out of the way — she builds in the background
      await load();
    } catch (e) { setErr(String(e)); }
    finally { setBuilding(null); }
  };

  // Keep the roster live while anything is still building. Cheap (one request),
  // and it stops as soon as nothing is in flight.
  const anyBuilding = characters.some((c) => c.status === "building");
  useEffect(() => {
    if (!anyBuilding) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [anyBuilding]);

  // Picking her face: validated server-side, then her body is generated from it.
  const choose = async (character, runId) => {
    setErr(null);
    setBuilding("Locking her face…");
    try {
      const res = await api.send(`/api/characters/${character.id}/master-face`,
                                 "POST", { run_id: runId });
      setBuilding("Generating her body…");
      for (;;) {
        await new Promise((r) => setTimeout(r, 1200));
        const st = await api.get(`/api/jobs/${res.job}`);
        if (st.done) break;       // a body failure is not fatal — she is usable
      }
      setPicking(null);
      await api.send("/api/characters/active", "PUT", { id: character.id }).catch(() => {});
      navigate(`/studio?char=${character.id}&tab=calibrate`);
    } catch (e) { setErr(String(e)); }
    finally { setBuilding(null); }
  };

  return (
    <div className="min-h-screen">
      {/* Hero header */}
      <header className="relative overflow-hidden border-b border-white/5">
        <div className="absolute inset-0 opacity-40">
          <div className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-rose-500/20 blur-[120px]" />
          <div className="absolute top-0 right-0 h-96 w-96 rounded-full bg-amber-400/10 blur-[120px]" />
        </div>
        <div className="relative px-6 md:px-12 py-14 md:py-20 max-w-6xl">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-[11px] text-zinc-400 ring-1 ring-white/10 mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            identity-gate active · ArcFace threshold
          </div>
          <h1 className="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05]">
            One face.
            <br />
            <span className="bg-gradient-to-r from-rose-300 via-amber-200 to-zinc-100 bg-clip-text text-transparent">
              Hundreds of shots.
            </span>
            <br />
            Zero drift.
          </h1>
          <p className="mt-6 max-w-xl text-zinc-400 text-[15px] leading-relaxed">
            Throughline is a character-asset pipeline that produces photorealistic images of the same fictional person across time, outfits, and poses — held together by a measured identity check, not a human eyeball.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 rounded-lg ring-1 ring-white/15 px-5 py-2.5 text-[13px] font-medium text-zinc-200 hover:bg-white/5 transition-colors"
            >
              <Plus className="h-4 w-4" strokeWidth={1.5} /> New character
            </button>
          </div>
        </div>
      </header>

      {/* Character picker */}
      <section className="px-6 md:px-12 py-10 max-w-6xl">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Characters</h2>
            <p className="text-[12px] text-zinc-500 mt-0.5">Each profile carries its own identity fingerprint and calibration.</p>
          </div>
          <span className="text-[12px] text-zinc-500 tabular-nums">{characters.length} profiles</span>
        </div>

        {err && (
          <div onClick={() => setErr(null)} className="mb-4 cursor-pointer rounded-lg ring-1 ring-rose-500/30 bg-rose-500/10 px-4 py-2 text-[12px] text-rose-300">
            {err} · dismiss
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {characters.map((c) => (
            <button
              key={c.id}
              onClick={() => enter(c)}
              className="group relative block text-left rounded-2xl overflow-hidden ring-1 ring-white/8 hover:ring-white/20 transition-all"
            >
              <div className="aspect-[4/5] relative overflow-hidden bg-zinc-900">
                {c.avatar ? (
                  <img src={c.avatar} alt={c.name} className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]" />
                ) : (
                  <div className="h-full w-full flex items-center justify-center bg-gradient-to-br from-zinc-800 to-zinc-900 text-4xl font-semibold text-zinc-600">
                    {c.initials}
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent" />
                <div className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-black/50 backdrop-blur px-2.5 py-1 text-[10px] font-medium ring-1 ring-white/10">
                  {/* No face is a harder state than "not calibrated": she cannot be
                      photographed at all until one is chosen, so it outranks. */}
                  {c.status === "building" ? (
                    <><Loader2 className="h-3 w-3 animate-spin text-sky-400" /> {c.job?.stage || "building"}</>
                  ) : c.status === "stalled" ? (
                    <><ShieldAlert className="h-3 w-3 text-rose-400" /> build failed</>
                  ) : !c.has_reference ? (
                    <><ShieldAlert className="h-3 w-3 text-rose-400" /> choose her face</>
                  ) : c.identityStatus === "identity_set" ? (
                    <><ShieldCheck className="h-3 w-3 text-emerald-400" /> identity set</>
                  ) : (
                    <><ShieldAlert className="h-3 w-3 text-amber-400" /> needs calibration</>
                  )}
                </div>
                <span onClick={(e) => rename(e, c)} title="rename character"
                  className="absolute top-3 right-10 z-10 rounded-md bg-black/50 p-1.5 text-zinc-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/80 hover:text-white">
                  <Pencil className="h-3.5 w-3.5" />
                </span>
                {characters.length > 1 && c.id !== active && (
                  <span onClick={(e) => remove(e, c)} title="delete character"
                    className="absolute top-3 right-3 z-10 rounded-md bg-black/50 p-1.5 text-rose-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/80">
                    <Trash2 className="h-3.5 w-3.5" />
                  </span>
                )}
                <div className="absolute bottom-0 inset-x-0 p-4">
                  <div className="text-[15px] font-semibold tracking-tight">{c.name}</div>
                  <div className="text-[11px] text-zinc-400 mt-0.5">Enter studio →</div>
                </div>
              </div>
            </button>
          ))}

          <button
            onClick={() => setShowCreate(true)}
            className="rounded-2xl ring-1 ring-dashed ring-white/15 hover:ring-white/30 hover:bg-white/[0.02] transition-all min-h-[260px] flex flex-col items-center justify-center gap-3 text-zinc-500 hover:text-zinc-300"
          >
            <div className="h-11 w-11 rounded-full ring-1 ring-white/15 flex items-center justify-center">
              <Plus className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <span className="text-[13px] font-medium">Create character</span>
          </button>
        </div>
      </section>

      {showCreate && <CreateDrawer onClose={() => !building && setShowCreate(false)} onCreate={create} building={building} />}
      {picking && <FacePicker {...picking} onChoose={choose} busy={building}
                        onCancel={() => setPicking(null)} />}
    </div>
  );
}

function labelFor(stage) {
  if (stage === "writing bio") return "Writing her bio…";
  if (stage === "generating body") return "Generating her body…";
  if (["generating face", "generating", "starting"].includes(stage)) return "Generating her first face…";
  if (stage === "gating") return "Checking her face…";
  if (/retry/i.test(stage || "")) return "Retrying (moderation)…";
  return STAGE[stage] || "Building her…";
}

function CreateDrawer({ onClose, onCreate, building }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [faceShape, setFaceShape] = useState(null);
  const [bodyType, setBodyType] = useState(null);
  const [height, setHeight] = useState(168);
  const [homeStyle, setHomeStyle] = useState("");
  const [homeSurroundings, setHomeSurroundings] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const ftIn = `${Math.floor(height / 30.48)}′${Math.round((height / 2.54) % 12)}″`;

  const pickFile = (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setFile(f); setPreview(URL.createObjectURL(f));
  };

  const submit = () => {
    if (!name.trim() || building) return;
    onCreate({ name: name.trim(), description, face_shape: faceShape, build: bodyType,
               height_cm: height, home_style: homeStyle, home_surroundings: homeSurroundings, file });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-[#0d0d0f] border-l border-white/5 overflow-y-auto">
        <div className="sticky top-0 bg-[#0d0d0f]/95 backdrop-blur border-b border-white/5 px-6 py-4 flex items-center justify-between z-10">
          <div>
            <h3 className="text-[15px] font-semibold">New character</h3>
            <p className="text-[11px] text-zinc-500 mt-0.5">Claude writes the bio, then generates faces for you to choose from.</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="px-6 py-6 space-y-6">
          <div>
            <label className="text-[12px] font-medium text-zinc-300">Name <span className="text-rose-400">*</span></label>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
              className="mt-1.5 w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none" placeholder="e.g. Aelira Vance" />
          </div>

          <div>
            <label className="text-[12px] font-medium text-zinc-300">Description</label>
            <p className="text-[10px] text-zinc-500 mb-1.5">Optional — left blank, Claude invents a coherent person.</p>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
              className="w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none resize-none" placeholder="Who is she?" />
          </div>

          <div>
            <label className="text-[12px] font-medium text-zinc-300">Face shape</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {FACE_SHAPES.map((f) => (
                <button key={f} onClick={() => setFaceShape(faceShape === f ? null : f)} className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors", faceShape === f ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{f}</button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-[12px] font-medium text-zinc-300">Body type</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {BODY_TYPES.map((b) => (
                <button key={b} onClick={() => setBodyType(bodyType === b ? null : b)} className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors", bodyType === b ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{b}</button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="text-[12px] font-medium text-zinc-300 flex items-center gap-1.5"><Ruler className="h-3.5 w-3.5" /> Height</label>
              <span className="text-[12px] text-zinc-300 tabular-nums">{height} cm · {ftIn}</span>
            </div>
            <input type="range" min={148} max={190} value={height} onChange={(e) => setHeight(+e.target.value)} className="w-full mt-2 accent-rose-400" />
          </div>

          <div>
            <label className="text-[12px] font-medium text-zinc-300">Style reference <span className="text-zinc-500 font-normal">(optional)</span></label>
            {preview ? (
              <div className="mt-1.5 flex items-center gap-3">
                <img src={preview} alt="reference" className="h-20 w-16 rounded-md object-cover ring-1 ring-white/15" />
                <button onClick={() => { setFile(null); setPreview(null); }} className="text-[12px] text-zinc-400 hover:text-rose-300 flex items-center gap-1"><X className="h-3.5 w-3.5" /> remove</button>
              </div>
            ) : (
              <label className="mt-1.5 rounded-lg border border-dashed border-white/15 px-4 py-6 flex flex-col items-center gap-2 text-center hover:border-white/30 cursor-pointer">
                <Upload className="h-5 w-5 text-zinc-500" />
                <p className="text-[11px] text-zinc-500">Upload a reference face image</p>
                <p className="text-[10px] text-zinc-600">Used only for hair, mood and lighting — never her face. She will be a different person.</p>
                <input type="file" accept="image/*" hidden onChange={pickFile} />
              </label>
            )}
          </div>

          {/* HOME — the third defining piece, alongside her bio and her body.
              Filling it in builds all ten corners now, so "her kitchen" means one
              specific kitchen from the first shot. Left blank it is skipped
              entirely rather than spending ten generations on generic rooms. */}
          <div className="pt-1 border-t border-white/5">
            <label className="text-[12px] font-medium text-zinc-300 flex items-center gap-1.5"><Home className="h-3.5 w-3.5" /> Her home</label>
            <p className="text-[10px] text-zinc-500 mb-1.5 mt-0.5">
              Filled in, all {HOME_CORNER_COUNT} corners generate now from this one style — her flat becomes a real place. Left blank, it's skipped and you build it later from the Home tab.
            </p>
            <textarea value={homeStyle} onChange={(e) => setHomeStyle(e.target.value)} rows={2}
              className="w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none resize-none"
              placeholder="Style and materials — e.g. a modern Bangalore flat, 12th floor, tile and marble floors, warm materials" />
            <input value={homeSurroundings} onChange={(e) => setHomeSurroundings(e.target.value)}
              className="mt-2 w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none"
              placeholder="What's visible outside (balcony/terrace/living room only)" />
            {homeStyle.trim() && (
              <p className="text-[10px] text-amber-300/80 mt-1.5">+{HOME_CORNER_COUNT} generations on submit — this takes a few minutes.</p>
            )}
          </div>

          <div className="rounded-lg bg-white/[0.03] ring-1 ring-white/5 p-3 flex gap-2.5">
            <Sparkles className="h-4 w-4 text-amber-300 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] text-zinc-400 leading-relaxed">
              On submit: bio → 4 face candidates{homeStyle.trim() ? " → home" : ""}. You pick her face, then her body is generated from it and she lands on the calibrate tab.
            </p>
          </div>
        </div>

        <div className="sticky bottom-0 bg-[#0d0d0f] border-t border-white/5 px-6 py-4 flex gap-3">
          <button onClick={onClose} disabled={!!building} className="flex-1 rounded-lg ring-1 ring-white/10 py-2.5 text-[13px] text-zinc-300 hover:bg-white/5 disabled:opacity-40">Cancel</button>
          <button onClick={submit} disabled={!name.trim() || !!building} className="flex-1 rounded-lg bg-white text-black py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center gap-2">
            {building ? <><Loader2 className="h-4 w-4 animate-spin" /> {building}</> : "Create character"}
          </button>
        </div>
      </div>
    </div>
  );
}
