import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, setApiCharacter, charView, STAGE } from "@/api/throughline";
import { ShieldCheck, ShieldAlert, Plus, X, Sparkles, Upload, Ruler, Trash2, Loader2, Pencil, Home, ChevronDown, ArrowRight } from "lucide-react";
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
  // The roster is not "inside" a character — clear any pin a studio left so
  // these listings answer for the real default rather than the last tab.
  useEffect(() => { setApiCharacter(null); load(); }, []);

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
      // Every identity picker, blank when unset — the backend reads blank as
      // "Claude decides" rather than as a value.
      fd.append("faces", String(form.faces ?? 4));
      fd.append("look", form.look || "");
      for (const k of ["age", "cheekbones", "jawline", "chin", "eyes", "brows",
                       "nose", "lips", "skin_tone", "skin_undertone",
                       "hair_colour", "hair_length", "hair_texture"]) {
        fd.append(k, form[k] || "");
      }
      fd.append("home_style", form.home_style || "");
      fd.append("home_surroundings", form.home_surroundings || "");
      fd.append("reference_mode", form.file ? (form.refMode || "inspiration") : "none");
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
      await api.send(`/api/characters/${character.id}/master-face`,
                     "POST", { run_id: runId });
      // Nothing to wait for: committing the face IS the step. No body reference
      // is generated here any more — it was a whole figure invented from a
      // head-and-shoulders photo, and it showed.
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

      {/* The composer used to live here as a card. It outgrew one: a scene has a
          cast, and every member of that cast has an outfit, a manicure, a
          hairstyle, makeup, accessories, shoes and a pose of her own, on top of a
          dozen axes the photograph itself has. It is its own page now. */}
      <div className="px-6 md:px-12 pt-10 max-w-6xl">
        <Link to="/collaborate"
          className="flex items-center justify-between rounded-2xl ring-1 ring-white/8 bg-white/[0.02] px-5 py-4 hover:ring-white/20 transition-colors group">
          <span>
            <span className="block text-[14px] font-medium">Collaborator Studio</span>
            <span className="block text-[11px] text-zinc-500 mt-0.5">
              Put two or more of them in one photograph — or compose a single shot with every axis available.
            </span>
          </span>
          <ArrowRight className="h-4 w-4 text-zinc-500 group-hover:text-white transition-colors" />
        </Link>
      </div>

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

// One collapsible group of pickers. Collapsed by default and showing how many of
// its axes are set, so the drawer stays a short form for anyone who just wants a
// name and a sentence — which is still the fast path.
function Section({ title, count, total, open, onToggle, children }) {
  return (
    <div className="rounded-lg ring-1 ring-white/8">
      <button onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left">
        <span className="text-[12px] font-medium text-zinc-300">{title}</span>
        <span className="flex items-center gap-2">
          <span className={cn("text-[10px]", count ? "text-emerald-300" : "text-zinc-600")}>
            {count ? `${count} of ${total} set` : "Claude decides"}
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 text-zinc-500 transition-transform",
                                     open && "rotate-180")} />
        </span>
      </button>
      {open && <div className="px-3 pb-3 space-y-3">{children}</div>}
    </div>
  );
}

// A row of mutually exclusive chips. Clicking the selected one clears it, which
// is how you get back to "Claude decides" without a separate control.
function Chips({ label, options, value, onChange }) {
  return (
    <div>
      <label className="text-[11px] text-zinc-400">{label}</label>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {(options || []).map((o) => (
          <button key={o} onClick={() => onChange(value === o ? null : o)}
            className={cn("rounded-full px-2.5 py-1 text-[11px] ring-1 transition-colors",
              value === o ? "bg-white text-black ring-white"
                          : "ring-white/10 text-zinc-400 hover:text-white")}>{o}</button>
        ))}
      </div>
    </div>
  );
}

function CreateDrawer({ onClose, onCreate, building }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [faceShape, setFaceShape] = useState(null);
  const [bodyType, setBodyType] = useState(null);
  const [height, setHeight] = useState(168);
  const [age, setAge] = useState(null);
  const [faces, setFaces] = useState(4);
  // "inspiration" = hair/mood only, she is a different person (4 generations).
  // "identity"    = the upload IS her face (0 generations).
  const [refMode, setRefMode] = useState("inspiration");
  const [look, setLook] = useState(null);
  const [homeStyle, setHomeStyle] = useState("");
  const [homeSurroundings, setHomeSurroundings] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const ftIn = `${Math.floor(height / 30.48)}′${Math.round((height / 2.54) % 12)}″`;

  // Vocabularies come from the backend so there is one copy of them. An option
  // the server cannot map must not be offered here.
  const [opts, setOpts] = useState(null);
  useEffect(() => { api.get("/api/characters/options").then(setOpts).catch(() => {}); }, []);
  const [picks, setPicks] = useState({});
  // A set, not a single value: in a modal there is room to have Face and
  // Skin & hair open together and compare, which the narrow drawer could not
  // afford. Closing one no longer collapses another.
  const [open, setOpen] = useState(() => new Set(["face", "skin", "body"]));
  const toggle = (k) => () => setOpen((s) => {
    const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n;
  });
  const set = (k) => (v) => setPicks((p) => ({ ...p, [k]: v }));
  const nSet = (keys) => keys.filter((k) => picks[k]).length;

  const pickFile = (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setFile(f); setPreview(URL.createObjectURL(f));
  };

  const submit = () => {
    if (!name.trim() || building) return;
    onCreate({ name: name.trim(), description, face_shape: faceShape, build: bodyType,
               height_cm: height, age: age || "", faces, look: look || "", refMode, ...picks,
               home_style: homeStyle, home_surroundings: homeSurroundings, file });
  };

  return (
    // A centred modal rather than a side drawer: the form grew from three
    // controls to sixteen, and a 28rem column made a two-column layout
    // impossible while pushing the sections below the fold. Matches FacePicker's
    // shell so both steps of creation look like the same flow.
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={() => !building && onClose()} />
      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col rounded-2xl bg-[#0d0d0f] ring-1 ring-white/10 overflow-hidden">
        <div className="border-b border-white/5 px-6 py-4 flex items-center justify-between">
          <div>
            <h3 className="text-[15px] font-semibold">New character</h3>
            <p className="text-[11px] text-zinc-500 mt-0.5">Claude writes the bio, then generates faces for you to choose from.</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        {/* Two columns once there is room for them. LEFT is the whole fast
            path — a name and a sentence is a complete character, and putting it
            alone in its own column says so. RIGHT is every optional picker,
            visible rather than hidden behind an accordion, because the screen
            can now show all sixteen at once and a control you have to go
            looking for may as well not exist. */}
        <div className="flex-1 overflow-y-auto grid lg:grid-cols-[340px_1fr] divide-y lg:divide-y-0 lg:divide-x divide-white/5">
          <div className="px-6 py-6 space-y-5">
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

          {/* The register every other field is chosen under, so it sits at the
              top with the description rather than among the pickers. It writes
              no part: an "attractiveness" field would put an adjective into
              every shot prompt, which is what makes an image model fall back on
              its generic beauty template. */}
          <div>
            <label className="text-[12px] font-medium text-zinc-300">Look</label>
            <p className="text-[10px] text-zinc-500 mb-1.5">How flattering her proportions should be. Steers the whole bio.</p>
            <div className="flex flex-wrap gap-1.5">
              {(opts?.looks || []).map((l) => (
                <button key={l} onClick={() => setLook(look === l ? null : l)}
                  className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors",
                    (look || opts?.default_look) === l ? "bg-white text-black ring-white"
                                                       : "ring-white/10 text-zinc-400 hover:text-white")}>{l}</button>
              ))}
            </div>
          </div>

          {/* Faces cost money; the upload does not. Hidden entirely when the
              upload IS her, because then there is nothing to generate and a
              "faces to generate" dial would be offering to spend on something
              already decided. */}
          <div className={cn(file && refMode === "identity" && "hidden")}>
            <div className="flex items-center justify-between">
              <label className="text-[12px] font-medium text-zinc-300">Faces to generate</label>
              <span className="text-[11px] text-zinc-500">{faces} generation{faces > 1 ? "s" : ""}</span>
            </div>
            <div className="mt-1.5 flex gap-1.5">
              {Array.from({ length: opts?.max_faces || 4 }, (_, i) => i + 1).map((n) => (
                <button key={n} onClick={() => setFaces(n)}
                  className={cn("flex-1 rounded-lg py-1.5 text-[12px] ring-1 transition-colors",
                    faces === n ? "bg-white text-black ring-white"
                                : "ring-white/10 text-zinc-400 hover:text-white")}>{n}</button>
              ))}
            </div>
            <p className="text-[10px] text-zinc-500 mt-1.5">You pick one as her master face; the rest are discarded.</p>
          </div>

          <div>
            <label className="text-[12px] font-medium text-zinc-300">Your own image <span className="text-zinc-500 font-normal">(optional)</span></label>
            {preview ? (
              <div className="mt-1.5 space-y-2">
                <div className="flex items-center gap-3">
                  <img src={preview} alt="reference" className="h-20 w-16 rounded-md object-cover ring-1 ring-white/15" />
                  <button onClick={() => { setFile(null); setPreview(null); }} className="text-[12px] text-zinc-400 hover:text-rose-300 flex items-center gap-1"><X className="h-3.5 w-3.5" /> remove</button>
                </div>

                {/* HOW the upload is used. The two modes are not variations of
                    one another — one spends four generations to invent a
                    different person, the other spends nothing and makes this
                    picture her. */}
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    { id: "identity", title: "This is her face", cost: "free",
                      blurb: "Used exactly as uploaded. No faces generated." },
                    { id: "inspiration", title: "Inspiration only", cost: `${faces} generation${faces > 1 ? "s" : ""}`,
                      blurb: "Hair, mood and lighting only. She will be a different person." },
                  ].map((m) => (
                    <button key={m.id} onClick={() => setRefMode(m.id)}
                      className={cn("rounded-lg px-2.5 py-2 text-left ring-1 transition-colors",
                        refMode === m.id ? "bg-white/[0.07] ring-white/40" : "ring-white/10 hover:ring-white/25")}>
                      <span className="flex items-baseline justify-between gap-1">
                        <span className="text-[11px] font-medium text-zinc-200">{m.title}</span>
                        <span className={cn("text-[9px]", m.cost === "free" ? "text-emerald-300" : "text-zinc-500")}>{m.cost}</span>
                      </span>
                      <span className="block text-[9px] text-zinc-500 leading-snug mt-0.5">{m.blurb}</span>
                    </button>
                  ))}
                </div>

                {refMode === "identity" ? (
                  <div className="rounded-lg ring-1 ring-amber-400/25 bg-amber-400/5 px-3 py-2 space-y-1.5">
                    <p className="text-[10px] text-amber-200/90 leading-relaxed">
                      <strong className="font-medium">She must be fictional.</strong> This image is used as her face
                      exactly as uploaded — nothing rewrites it. Do not upload a photograph of a real person.
                    </p>
                    <p className="text-[10px] text-zinc-400 leading-relaxed">
                      <strong className="font-medium text-zinc-300">For the best results, calibrate her next.</strong>{" "}
                      One upload is a single angle. Calibration generates her at twelve
                      head angles and builds the identity gallery every later shot is
                      scored against — that is where consistency actually comes from.
                    </p>
                  </div>
                ) : (
                  <p className="text-[10px] text-zinc-600 leading-relaxed">
                    Her face comes from the pickers above, not from this image — the upload only
                    steers hair, mood and lighting.
                  </p>
                )}
              </div>
            ) : (
              <label className="mt-1.5 rounded-lg border border-dashed border-white/15 px-4 py-6 flex flex-col items-center gap-2 text-center hover:border-white/30 cursor-pointer">
                <Upload className="h-5 w-5 text-zinc-500" />
                <p className="text-[11px] text-zinc-500">Upload a face image</p>
                <p className="text-[10px] text-zinc-600">Use it as her face and generate nothing, or as style inspiration only. You choose after uploading.</p>
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

          </div>

          <div className="px-6 py-6 space-y-5">
            <div className="flex items-baseline justify-between">
              <h4 className="text-[12px] font-medium text-zinc-300">Refine her</h4>
              <span className="text-[10px] text-zinc-500">optional — Claude decides anything left blank</span>
            </div>
          <Section title="Face" total={8}
            count={nSet(["cheekbones","jawline","chin","eyes","brows","nose","lips"]) + (faceShape ? 1 : 0)}
            open={open.has("face")} onToggle={toggle("face")}>
            <Chips label="Face shape" options={opts?.face_shapes || FACE_SHAPES}
                   value={faceShape} onChange={setFaceShape} />
            {/* The skull first — it is what makes a face recognisable, and what a
                drifted generation loses before it loses eye colour. */}
            <Chips label="Cheekbones" options={opts?.pickers?.cheekbones} value={picks.cheekbones} onChange={set("cheekbones")} />
            <Chips label="Jawline"    options={opts?.pickers?.jawline}    value={picks.jawline}    onChange={set("jawline")} />
            <Chips label="Chin"       options={opts?.pickers?.chin}       value={picks.chin}       onChange={set("chin")} />
            <Chips label="Eyes"       options={opts?.pickers?.eyes}       value={picks.eyes}       onChange={set("eyes")} />
            <Chips label="Brows"      options={opts?.pickers?.brows}      value={picks.brows}      onChange={set("brows")} />
            <Chips label="Nose"       options={opts?.pickers?.nose}       value={picks.nose}       onChange={set("nose")} />
            <Chips label="Lips"       options={opts?.pickers?.lips}       value={picks.lips}       onChange={set("lips")} />
          </Section>

          <Section title="Skin & hair" total={5}
            count={nSet(["skin_tone","skin_undertone","hair_colour","hair_length","hair_texture"])}
            open={open.has("skin")} onToggle={toggle("skin")}>
            <Chips label="Skin tone"      options={opts?.skin_tones}      value={picks.skin_tone}      onChange={set("skin_tone")} />
            <Chips label="Undertone"      options={opts?.skin_undertones} value={picks.skin_undertone} onChange={set("skin_undertone")} />
            <Chips label="Hair colour"    options={opts?.pickers?.hair_colour}  value={picks.hair_colour}  onChange={set("hair_colour")} />
            <Chips label="Hair length"    options={opts?.pickers?.hair_length}  value={picks.hair_length}  onChange={set("hair_length")} />
            <Chips label="Hair texture"   options={opts?.pickers?.hair_texture} value={picks.hair_texture} onChange={set("hair_texture")} />
          </Section>

          <Section title="Body & age" total={3} count={(bodyType ? 1 : 0) + 1 + (age ? 1 : 0)}
            open={open.has("body")} onToggle={toggle("body")}>
            <Chips label="Body type" options={opts?.builds || BODY_TYPES}
                   value={bodyType} onChange={setBodyType} />
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] text-zinc-400 flex items-center gap-1.5"><Ruler className="h-3 w-3" /> Height</label>
                <span className="text-[11px] text-zinc-300 tabular-nums">{height} cm · {ftIn}</span>
              </div>
              <input type="range" min={148} max={190} value={height} onChange={(e) => setHeight(+e.target.value)} className="w-full mt-1.5 accent-rose-400" />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] text-zinc-400">Age</label>
                <span className="text-[11px] text-zinc-300 tabular-nums">{age ? `${age}` : "Claude decides"}</span>
              </div>
              <input type="range" min={18} max={60} value={age || 26}
                onChange={(e) => setAge(+e.target.value)} className="w-full mt-1.5 accent-rose-400" />
              {age && <button onClick={() => setAge(null)} className="mt-1 text-[10px] text-zinc-500 hover:text-zinc-300">clear</button>}
            </div>
          </Section>

          </div>
        </div>

        <div className="border-t border-white/5 px-6 py-4 flex items-center gap-3">
          <p className="hidden sm:flex flex-1 items-start gap-2 text-[11px] text-zinc-500 leading-relaxed">
            <Sparkles className="h-3.5 w-3.5 text-amber-300 flex-shrink-0 mt-0.5" />
            {(() => {
              const own = file && refMode === "identity";
              const n = (own ? 0 : faces) + (homeStyle.trim() ? HOME_CORNER_COUNT : 0);
              return (
                <>
                  bio → {own ? "her face (uploaded)" : `${faces} face${faces > 1 ? "s" : ""}`}
                  {homeStyle.trim() ? ` → ${HOME_CORNER_COUNT} home corners` : ""}.{" "}
                  <span className={n === 0 ? "text-emerald-300" : ""}>
                    {n === 0 ? "No generations — free." : `${n} generation${n > 1 ? "s" : ""}.`}
                  </span>{" "}
                  {own ? "She is shootable immediately; calibrate her next."
                       : "You pick her face, then calibrate her."}
                </>
              );
            })()}
          </p>
          <button onClick={onClose} disabled={!!building} className="rounded-lg ring-1 ring-white/10 px-5 py-2.5 text-[13px] text-zinc-300 hover:bg-white/5 disabled:opacity-40">Cancel</button>
          <button onClick={submit} disabled={!name.trim() || !!building} className="rounded-lg bg-white text-black px-6 py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center gap-2">
            {building ? <><Loader2 className="h-4 w-4 animate-spin" /> {building}</> : "Create character"}
          </button>
        </div>
      </div>
    </div>
  );
}
