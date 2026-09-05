import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/throughline";
import { Loader2, Sparkles, X, Wand2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import CastRow from "@/components/collab/CastRow";
import Picker from "@/components/collab/Picker";
import BrowsePicker from "@/components/collab/BrowsePicker";
import ModelPicker from "@/components/ModelPicker";

// COLLABORATOR STUDIO — compose a photograph of one or more of them.
//
// The landing page used to hold a small version of this. It outgrew the card:
// a scene has a cast, and every member of that cast has an outfit, a manicure, a
// hairstyle, makeup, accessories, shoes and a pose of her own, on top of a dozen
// axes the photograph itself has. That is a page, not a panel.
//
// The organising idea is that every choice here has a COST and the cost is shown
// before it is paid. Image references are measured against identity (2 refs
// 0.622, 3 refs 0.579); framing decides how many pixels a face gets, and a face
// under 400px measures 0.548 against 0.612 above it. The right column exists to
// say so while there is still time to change your mind.

const EMPTY_MEMBER = { outfit: null, nail: null, hair: "", makeup: "",
                       accessories: [], footwear: "", pose: "" };

export default function Collaborate() {
  const [characters, setCharacters] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [cast, setCast] = useState([]);
  const [lib, setLib] = useState(null);
  const [members, setMembers] = useState({});   // {cid: {...EMPTY_MEMBER}}

  // the photograph's own axes
  const [shotType, setShotType] = useState("candid");
  const [framing, setFraming] = useState("");
  const [aspect, setAspect] = useState("3:4");
  const [resolution, setResolution] = useState("4K");
  const [place, setPlace] = useState("");
  const [interaction, setInteraction] = useState("");
  const [activity, setActivity] = useState("");
  const [lighting, setLighting] = useState("");
  const [timeOfDay, setTimeOfDay] = useState("");
  const [weather, setWeather] = useState("");
  const [season, setSeason] = useState("");
  const [holder, setHolder] = useState("");
  const [flaws, setFlaws] = useState("");
  const [faceAcc, setFaceAcc] = useState(true);
  // Background people. OFF by default because the gate scores whichever face
  // best matches the gallery, so bystanders are extra chances to score a
  // stranger and call it her — a club brief once returned NINE faces. But the
  // server-side default alone made a crowd unaskable from the UI, and "blurred
  // crowd behind us" is a legitimate thing to want from a nightclub selfie.
  const [allowCrowd, setAllowCrowd] = useState(false);
  const [safety, setSafety] = useState("");   // fal moderation dial, 1-6

  const [seed, setSeed] = useState("");
  const [modes, setModes] = useState({});
  const [draft, setDraft] = useState("");        // AI-written, editable

  const [preview, setPreview] = useState(null);
  const [showMoments, setShowMoments] = useState(false);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);
  const box = useRef(null);

  useEffect(() => { api.get("/api/characters").then((d) => setCharacters(d.characters || [])).catch(() => {}); }, []);

  // The cast is resolved SERVER-side even though a regex here would look
  // identical. It would not stay identical: the server's parser is the one that
  // builds the prompt, and a divergence shows up as an outfit on the wrong woman.
  useEffect(() => {
    const t = setTimeout(async () => {
      try { setCast((await api.send("/api/scene/cast", "POST", { prompt })).cast || []); }
      catch { /* mid-sentence is not an error */ }
    }, 300);
    return () => clearTimeout(t);
  }, [prompt]);

  useEffect(() => {
    if (!cast.length) { setLib(null); return; }
    api.get(`/api/scene/library?cast=${cast.length}&owner=${cast[0].id}`)
       .then(setLib).catch(() => {});
  }, [cast.length, cast[0]?.id]);

  const member = (cid) => members[cid] || EMPTY_MEMBER;
  const framingOrder = lib?.framing?.findIndex((f) => f.id === framing) + 1 || 0;

  // null follows the project default; set per scene without changing it.
  const [model, setModel] = useState(null);

  const body = useMemo(() => ({
    prompt, place, activity, interaction, holder, flaws, shot_type: shotType,
    framing, aspect, resolution, lighting, time_of_day: timeOfDay, weather, season,
    face_accessories: faceAcc, allow_crowd: allowCrowd,
    safety_tolerance: safety || null,
    seed: seed === "" ? null : Number(seed),
    prompt_override: draft.trim() || null,
    wardrobe: pick(members, "outfit"), nails: pick(members, "nail"),
    hair: pick(members, "hair"), makeup: pick(members, "makeup"),
    footwear: pick(members, "footwear"), poses: pick(members, "pose"),
    accessories: Object.fromEntries(
      Object.entries(members).map(([k, v]) => [k, v.accessories || []]).filter(([, v]) => v.length)),
    as_image: Object.fromEntries(Object.entries(modes).map(([k, v]) => [k, v !== "text"])),
    model,
  }), [prompt, place, activity, interaction, holder, flaws, shotType, framing, aspect,
       resolution, lighting, timeOfDay, weather, season, faceAcc, allowCrowd, safety, seed, draft, members, modes, model]);

  // The right column renders what the SERVER will actually do, not a guess.
  useEffect(() => {
    if (!cast.length) { setPreview(null); return; }
    const t = setTimeout(() => {
      api.send("/api/scene/preview", "POST", body).then(setPreview).catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(t);
  }, [body, cast.length]);

  const applyMoment = (m) => {
    setPlace(m.place || ""); setActivity(m.activity || "");
    setInteraction(cast.length > 1 ? (m.interaction || "") : "");
    setHolder(m.holder || ""); setFlaws(m.flaws || "");
    setShotType(m.shot_type || "candid");
    if (m.framing) setFraming(m.framing);
    if (m.lighting) setLighting(m.lighting);
    if (m.time_of_day) setTimeOfDay(m.time_of_day);
    setShowMoments(false);
  };

  const insert = (id) => {
    const el = box.current;
    const at = el?.selectionStart ?? prompt.length;
    setPrompt(`${prompt.slice(0, at)}@${id} ${prompt.slice(at)}`);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + id.length + 2, at + id.length + 2); });
  };

  const writeWithClaude = async () => {
    setErr(null); setBusy("Claude is writing…");
    try { setDraft((await api.send("/api/scene/ai-prompt", "POST", body)).prompt || ""); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  };

  const generate = async () => {
    setErr(null); setResult(null); setBusy("Composing…");
    try {
      const { job } = await api.send("/api/scene", "POST", body);
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await api.get(`/api/jobs/${job}`);
        setBusy(`${st.stage}…`);
        if (st.done) { st.error ? setErr(st.error) : setResult(st.run); break; }
      }
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  };

  const v = result?.verdict;
  const px = preview?.face_px ?? 0;
  const plateau = preview?.plateau_px ?? 400;
  const ready = cast.length > 0 && cast.every((c) => c.has_reference);

  return (
    <div className="px-5 md:px-8 py-7 max-w-[1700px] mx-auto">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h1 className="text-[24px] font-semibold tracking-[-0.4px] leading-none text-ink">Scenes</h1>
          <p className="text-[12px] text-zinc-500 mt-0.5">
            Two or more of them in one photograph. Name anyone with @ — the cast, and everything each of them needs, follows.
          </p>
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_360px] gap-5 items-start">

        {/* ---------------------------------------------------------- BRIEF */}
        <section className="space-y-3">
          <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-4">
            <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">The brief</span>
            <textarea ref={box} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5}
              placeholder="@kiara @alexa and @ridhi at an ice cream parlour in a Pune mall…"
              className="mt-2 w-full rounded-lg bg-white/5 ring-1 ring-line px-3 py-2.5 text-[13px] focus:ring-white/30 outline-none resize-none" />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {characters.filter((c) => c.has_reference).map((c) => (
                <button key={c.id} onClick={() => insert(c.id)}
                  className="rounded-full px-2.5 py-1 text-[11px] ring-1 ring-line text-zinc-400 hover:text-white hover:ring-white/25">
                  @{c.id}
                </button>
              ))}
            </div>
          </div>

          {lib && (
            <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-4">
              <button onClick={() => setShowMoments(!showMoments)}
                className="w-full flex items-center justify-between text-left">
                <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">Scenarios</span>
                <span className="text-[10px] text-zinc-500">
                  {showMoments ? "hide" : "one click fills everything"}
                </span>
              </button>
              {showMoments && (
                <div className="mt-3 space-y-3 max-h-[420px] overflow-y-auto">
                  {Object.entries(lib.moments).map(([group, items]) => (
                    <div key={group}>
                      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">{group}</div>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((m) => (
                          <button key={m.id} onClick={() => applyMoment(m)} title={m.activity}
                            className="rounded-lg px-2.5 py-1.5 text-[11px] ring-1 ring-line text-zinc-300 hover:ring-white/30 hover:bg-white/5">
                            {m.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* The written prompt. Claude drafts it; you edit it; it is used
              VERBATIM when present. The references do not change, so the @imageN
              tags it was written against still point where it thinks they do. */}
          <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-4">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">Written prompt</span>
              <div className="flex items-center gap-2">
                {draft && (
                  <button onClick={() => setDraft("")} title="Go back to the assembled prompt"
                    className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-1">
                    <RotateCcw className="h-3 w-3" /> discard
                  </button>
                )}
                <button onClick={writeWithClaude} disabled={!ready || !!busy}
                  className="rounded-full px-2.5 py-1 text-[10px] ring-1 ring-white/15 text-zinc-300 hover:bg-white/5 disabled:opacity-40 flex items-center gap-1">
                  <Wand2 className="h-3 w-3" /> Write with Claude
                </button>
              </div>
            </div>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={draft ? 10 : 3}
              placeholder="Empty = built from the pickers below. Write or generate one here and it is used exactly as typed."
              className="mt-2 w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2.5 text-[12px] font-mono leading-relaxed focus:ring-white/30 outline-none resize-none" />
          </div>
        </section>

        {/* ------------------------------------------------------ CAST + AXES */}
        <section className="space-y-3">
          {cast.length === 0 && (
            <div className="rounded-xl bg-surface ring-1 ring-line-subtle px-5 py-10 text-center">
              <div className="text-[13px] font-medium text-ink">No cast yet</div>
              <p className="mx-auto mt-1.5 max-w-[320px] text-[13px] text-ink-subtle leading-relaxed">
                Type <span className="text-ink-muted">@</span> and a name in the brief.
                Everything each of them wears, does and stands in appears here.
              </p>
            </div>
          )}
          {cast.length > 0 && (
            <div className="space-y-2">
              {cast.map((c) => c.has_reference ? (
                <CastRow key={c.id} character={c} lib={lib} framingOrder={framingOrder}
                  value={member(c.id)}
                  onChange={(v) => setMembers((m) => ({ ...m, [c.id]: v }))} />
              ) : (
                <div key={c.id} className="flex items-center gap-3 rounded-xl ring-1 ring-rose-500/25 bg-rose-500/[0.07] px-3 py-2.5">
                  <span className="flex-1 text-[13px] text-rose-200">
                    {c.name} has no master face yet
                  </span>
                  <a href={`/studio?char=${encodeURIComponent(c.id)}`}
                    className="shrink-0 rounded-md bg-white/10 px-2.5 py-1 text-[11px] text-ink-muted hover:bg-white/15">
                    Fix her face →
                  </a>
                </div>
              ))}
            </div>
          )}

          {lib && (
            <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-4 space-y-3">
              <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">The photograph</span>

              <div className="grid grid-cols-2 gap-2">
                <Picker label="Register" flat={lib.shot_types} value={shotType}
                  onChange={(v) => setShotType(v || "candid")} empty="candid" />
                {/* Framing carries its predicted face size at THIS cast, because
                    that number decides whether the gate can say anything at all
                    about the result. */}
                <Picker label="Framing" value={framing} onChange={setFraming}
                  empty="whatever the model decides"
                  flat={lib.framing.map((f) => ({ id: f.id, label: `${f.label} · ~${f.face_px}px` }))} />
                <Picker label="Frame size" flat={lib.aspects} value={aspect}
                  onChange={(v) => setAspect(v || "3:4")} empty="3:4" />
                <Picker label="Resolution" value={resolution}
                  onChange={(v) => setResolution(v || "4K")} empty="4K"
                  flat={lib.resolutions.map((r) => ({ id: r, label: r }))} />
                <Picker label="Where" flat={lib.places.map((p) => ({
                    id: p.key, label: p.label + (p.has_image ? "" : " (described)") }))}
                  value={place} onChange={setPlace} empty="wherever the brief says" />
                <div />
              </div>

              {/* THE ARRANGEMENT. Not a dropdown: 250 entries, and which one is
                  chosen is measured to move identity by 5x (cheek-to-cheek 0.118
                  against both-to-camera 0.572, same everything else). The text
                  has to be readable before it is chosen. */}
              {cast.length > 1 && (
                <BrowsePicker label="Together" hint="how the cast is arranged"
                  groups={lib.interactions} selected={interaction}
                  onSelect={setInteraction} emptyLabel="however the scene reads" />
              )}

              <label className="block">
                <span className="text-[10px] text-zinc-500">Doing</span>
                <input value={activity} onChange={(e) => setActivity(e.target.value)}
                  placeholder="what is happening"
                  className="mt-1 w-full rounded-lg bg-white/5 ring-1 ring-line px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30" />
              </label>

              <div className="grid grid-cols-2 gap-2">
                <Picker label="Light" groups={lib.lighting} value={lighting} onChange={setLighting} />
                <Picker label="Hour" flat={lib.time_of_day} value={timeOfDay} onChange={setTimeOfDay} />
                <Picker label="Weather" flat={lib.weather} value={weather} onChange={setWeather} />
                <Picker label="Season" flat={lib.season} value={season} onChange={setSeason} />
                <Picker label="Camera" flat={lib.holders.map((h) => ({ id: h.id, label: h.label }))}
                  value={holder} onChange={setHolder} empty="unspecified" />
                {/* fal's own dial. Per-request by design (11b4f1a) and never
                    given a control until now — every scene shipped on the
                    provider default. */}
                <Picker label="Moderation" value={safety} onChange={setSafety}
                  empty="default (4)"
                  flat={[1, 2, 3, 4, 5, 6].map((n) => ({
                    id: String(n),
                    label: `${n}${n === 1 ? " — strictest" : n === 6 ? " — loosest" : ""}`,
                  }))} />
                <Picker label="Imperfection" flat={lib.flaws.map((f) => ({ id: f.id, label: f.label }))}
                  value={flaws} onChange={setFlaws} empty="clean" />
              </div>

              <div className="flex items-center gap-4 pt-1">
                {/* An identity lever, not a style toggle: dark lenses remove the
                    eye region, which is where ArcFace reads hardest. */}
                <button onClick={() => setFaceAcc(!faceAcc)}
                  className="flex items-center gap-2 text-[11px] text-zinc-400 hover:text-zinc-200">
                  <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors",
                    faceAcc ? "bg-emerald-500/80" : "bg-white/10")}>
                    <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      faceAcc ? "translate-x-4" : "translate-x-0")} />
                  </span>
                  Face accessories
                </button>
                {/* Also an identity lever. Every extra face is another candidate
                    for the gate to score, and it scores whichever one best
                    matches the gallery — so a crowd makes the verdict a lottery
                    rather than a measurement. Off by default; on when the
                    photograph is genuinely of a room. */}
                <button onClick={() => setAllowCrowd(!allowCrowd)}
                  title="Let the scene contain background people. Raises faces in frame, which the gate cannot tell apart from her."
                  className="flex items-center gap-2 text-[11px] text-zinc-400 hover:text-zinc-200">
                  <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors",
                    allowCrowd ? "bg-amber-500/80" : "bg-white/10")}>
                    <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      allowCrowd ? "translate-x-4" : "translate-x-0")} />
                  </span>
                  Background people
                </button>
                <label className="flex items-center gap-1.5 text-[11px] text-zinc-500">
                  seed
                  <input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))}
                    placeholder="random"
                    className="w-24 rounded-lg bg-white/5 ring-1 ring-line px-2 py-1 text-[11px] outline-none focus:ring-white/30" />
                </label>
              </div>
            </div>
          )}
        </section>

        {/* --------------------------------------------------------- OUTPUT */}
        <section className="space-y-3 lg:sticky lg:top-5">
          {preview && (
            <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-4 space-y-3">
              <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">What this will cost</span>

              {/* THE LEDGER. Every image reference is measured off the identity,
                  and every optional one has a text form good enough to fall back
                  to. Showing what is attached turns an invisible tax into a choice. */}
              <div className="flex flex-wrap gap-1.5">
                {preview.ledger.map((l, i) => (
                  <span key={i} className={cn("rounded-full px-2 py-0.5 text-[10px] ring-1",
                    l.mode === "image" ? "ring-emerald-400/30 text-emerald-300"
                      : l.mode === "dropped" ? "ring-white/5 text-zinc-600 line-through"
                      : "ring-line text-zinc-500")}>
                    {l.mode === "image" ? l.tag : l.mode} · {l.label}
                  </span>
                ))}
              </div>
              <p className="text-[10px] text-zinc-500">
                {preview.images} image reference{preview.images === 1 ? "" : "s"}
                {preview.images > 2 && " — past two, identity measurably weakens (0.622 at two, 0.579 at three)"}
              </p>

              {/* The predicted face size. An estimate, calibrated on one real
                  measurement, and the thing that decides whether the gate can
                  say anything about the result at all. */}
              <div className="rounded-lg ring-1 ring-line-subtle px-3 py-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-[10px] text-zinc-500">estimated face size</span>
                  <span className={cn("text-[13px] font-medium",
                    px >= plateau ? "text-emerald-300" : px >= 250 ? "text-amber-300" : "text-rose-300")}>
                    ~{px}px
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-zinc-500 leading-relaxed">
                  {px >= plateau
                    ? `above the ${plateau}px plateau — measured 0.612 here against 0.548 below`
                    : px >= 250
                      ? `under the ${plateau}px plateau — measured 0.548 in this band against 0.612 above`
                      : "below 250px — measured 0.472, and near the gate's 160px abstain floor"}
                </p>
              </div>

              <details className="text-[10px] text-zinc-500">
                <summary className="cursor-pointer hover:text-zinc-300">the prompt</summary>
                <p className="mt-2 font-mono leading-relaxed text-zinc-400 max-h-64 overflow-y-auto whitespace-pre-wrap">
                  {preview.prompt}
                </p>
              </details>
            </div>
          )}

          {err && (
            <div className="rounded-lg bg-rose-500/10 ring-1 ring-rose-500/20 px-3 py-2 text-[11px] text-rose-200">
              {err} <button onClick={() => setErr(null)} className="ml-1 underline">dismiss</button>
            </div>
          )}

          <ModelPicker value={model} onChange={setModel} className="mb-3" />

          <button onClick={generate} disabled={!ready || !!busy}
            className="w-full rounded-lg bg-white text-black px-5 py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center gap-2">
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> {busy}</>
                  : <><Sparkles className="h-4 w-4" /> Generate</>}
          </button>
          {cast.length > 1 && (
            <p className="text-[10px] text-zinc-600 text-center">
              owned by {cast[0].name} · everyone sees it in their own review
            </p>
          )}

          {result && (
            <div className="rounded-2xl ring-1 ring-line-subtle bg-surface p-3 space-y-2">
              {/* An <img>, so the owner travels in the URL — a header cannot. */}
              <img src={`/api/images/${result.file}?character=${cast[0]?.id || ""}`} alt=""
                   className="w-full rounded-lg ring-1 ring-line" />
              <div className="text-[11px] space-y-1">
                <div className={cn("font-medium", v?.status === "kept" ? "text-emerald-300" : "text-amber-300")}>
                  {v?.status}
                </div>
                {(v?.cast || []).map((m) => (
                  <div key={m.character} className="text-zinc-400">
                    {m.character}: {m.similarity} · {m.face_px}px · yaw {m.yaw}
                  </div>
                ))}
                {v?.similarity != null && <div className="text-zinc-400">{v.similarity} · {v.face_px}px</div>}
                {v?.distinctness != null && (
                  <div className={cn(v.blended ? "text-rose-300" : "text-zinc-500")}>
                    distinctness {v.distinctness} {v.blended ? "— BLENDED" : "— distinct"}
                  </div>
                )}
                <button onClick={() => setResult(null)}
                  className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 pt-1">
                  <X className="h-3 w-3" /> clear
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

// {cid: {...}} -> {cid: value}, dropping the empties so the request stays small
// and the server's "unset" branch is actually reached.
function pick(members, key) {
  return Object.fromEntries(
    Object.entries(members).map(([k, v]) => [k, v[key]]).filter(([, v]) => v));
}
