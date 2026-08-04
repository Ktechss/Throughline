import React, { useEffect, useRef, useState } from "react";
import { api } from "@/api/throughline";
import { Loader2, Sparkles, X, MapPin, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import CastWardrobe from "./CastWardrobe";

// Write the scene, and the CAST falls out of the text. "@kiara and @sonam on a
// rooftop" is a two-hander — the right shape for a photograph of several people,
// and why this lives on the landing page rather than inside one studio.
//
// The cast is resolved SERVER-side even though a regex here would look identical.
// It would not stay identical: the server's parser is the one that builds the
// prompt, and a divergence shows up as an outfit attached to the wrong woman.
export default function SceneComposer({ characters, onDone }) {
  const [prompt, setPrompt] = useState("");
  const [cast, setCast] = useState([]);
  const [lib, setLib] = useState(null);
  const [ledger, setLedger] = useState([]);

  // the scene's axes — a moment fills these; every one stays editable
  const [wardrobe, setWardrobe] = useState({});
  const [modes, setModes] = useState({});        // {"outfit:kiara": "image"|"text", place: …}
  const [place, setPlace] = useState("");
  const [activity, setActivity] = useState("");
  const [interaction, setInteraction] = useState("");
  const [pose, setPose] = useState("");
  const [holder, setHolder] = useState("");
  const [flaws, setFlaws] = useState("");
  const [shotType, setShotType] = useState("candid");

  const [showMoments, setShowMoments] = useState(false);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);
  const box = useRef(null);

  // Re-resolve as you type. Cheap, and it keeps the cast rows honest while the
  // sentence is still being written.
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await api.send("/api/scene/cast", "POST", { prompt });
        setCast(r.cast || []);
      } catch { /* mid-sentence is not an error */ }
    }, 300);
    return () => clearTimeout(t);
  }, [prompt]);

  // Libraries are filtered by cast SIZE server-side: a two-person interaction
  // must never be offered to a solo scene, and the client should not know the rule.
  useEffect(() => {
    if (!cast.length) { setLib(null); return; }
    api.get(`/api/scene/library?cast=${cast.length}&owner=${cast[0].id}`)
       .then(setLib).catch(() => {});
  }, [cast.length, cast[0]?.id]);

  const body = () => ({
    prompt, wardrobe, place, activity, interaction, pose,
    holder, flaws, shot_type: shotType,
    as_image: Object.fromEntries(Object.entries(modes).map(([k, v]) => [k, v !== "text"])),
  });

  // The ledger is what the SERVER will actually attach — not a guess made here.
  useEffect(() => {
    if (!cast.length) { setLedger([]); return; }
    const t = setTimeout(() => {
      api.send("/api/scene/preview", "POST", body())
         .then((d) => setLedger(d.ledger || [])).catch(() => setLedger([]));
    }, 250);
    return () => clearTimeout(t);
  }, [prompt, wardrobe, modes, place, activity, interaction, pose, holder, flaws, cast.length]);

  const applyMoment = (m) => {
    setPlace(m.place || "");
    setActivity(m.activity || "");
    setPose(m.pose || "");
    setInteraction(cast.length > 1 ? (m.interaction || "") : "");
    setHolder(m.holder || "");
    setFlaws(m.flaws || "");
    setShotType(m.shot_type || "candid");
    setShowMoments(false);
  };

  const insert = (id) => {
    const el = box.current;
    const at = el?.selectionStart ?? prompt.length;
    setPrompt(`${prompt.slice(0, at)}@${id} ${prompt.slice(at)}`);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + id.length + 2, at + id.length + 2); });
  };

  const images = ledger.filter((l) => l.mode === "image").length;

  const generate = async () => {
    setErr(null); setResult(null); setBusy("Composing…");
    try {
      const { job } = await api.send("/api/scene", "POST", body());
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await api.get(`/api/jobs/${job}`);
        setBusy(`${st.stage}…`);
        if (st.done) { st.error ? setErr(st.error) : setResult(st.run); break; }
      }
      onDone?.();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  };

  const v = result?.verdict;
  const field = "w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30";

  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-[15px] font-semibold tracking-tight">Compose a scene</h2>
        <span className="text-[11px] text-zinc-500">name anyone with @ — the cast follows</span>
      </div>

      <textarea ref={box} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
        placeholder="@kiara and @sonam on a Sunday morning…"
        className="w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2.5 text-[13px] focus:ring-white/30 outline-none resize-none" />

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {characters.filter((c) => c.has_reference).map((c) => (
          <button key={c.id} onClick={() => insert(c.id)}
            className="rounded-full px-2.5 py-1 text-[11px] ring-1 ring-white/10 text-zinc-400 hover:text-white hover:ring-white/25">
            @{c.id}
          </button>
        ))}
        {cast.length > 0 && lib && (
          <button onClick={() => setShowMoments(!showMoments)}
            className={cn("ml-auto rounded-full px-3 py-1 text-[11px] ring-1 transition-colors",
              showMoments ? "bg-white text-black ring-white" : "ring-white/15 text-zinc-300 hover:bg-white/5")}>
            ✦ Moments
          </button>
        )}
      </div>

      {/* A moment is a whole slice of a day — place, activity, arrangement,
          camera, imperfection — in one click. Everything it sets stays editable
          below: a preset is a starting point, not a decision. */}
      {showMoments && lib && (
        <div className="mt-3 rounded-xl ring-1 ring-white/8 p-3 max-h-72 overflow-y-auto space-y-3">
          {Object.entries(lib.moments).map(([group, items]) => (
            <div key={group}>
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">{group}</div>
              <div className="flex flex-wrap gap-1.5">
                {items.map((m) => (
                  <button key={m.id} onClick={() => applyMoment(m)} title={m.activity}
                    className="rounded-lg px-2.5 py-1.5 text-[11px] ring-1 ring-white/10 text-zinc-300 hover:ring-white/30 hover:bg-white/5">
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {cast.length > 0 && (
        <div className="mt-4 space-y-3">
          <div className="space-y-2">
            {cast.map((c) => c.has_reference ? (
              <CastWardrobe key={c.id} character={c} selected={wardrobe[c.id] || null}
                mode={modes[`outfit:${c.id}`] || "image"}
                onMode={(m) => setModes((s) => ({ ...s, [`outfit:${c.id}`]: m }))}
                onSelect={(id) => setWardrobe((w) => ({ ...w, [c.id]: id || undefined }))} />
            ) : (
              <div key={c.id} className="rounded-xl ring-1 ring-rose-500/20 bg-rose-500/5 px-3 py-2 text-[11px] text-rose-200">
                {c.name} has no master face yet — choose one before shooting her
              </div>
            ))}
          </div>

          {lib && (
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block">
                <span className="text-[10px] text-zinc-500 flex items-center gap-1"><MapPin className="h-3 w-3" /> Where</span>
                <select value={place} onChange={(e) => setPlace(e.target.value)} className={cn(field, "mt-1")}>
                  <option value="">wherever the scene says</option>
                  {lib.places.map((p) => (
                    <option key={p.key} value={p.key}>{p.label}{p.has_image ? "" : " (no photo — described)"}</option>
                  ))}
                </select>
              </label>

              {cast.length > 1 ? (
                <label className="block">
                  <span className="text-[10px] text-zinc-500 flex items-center gap-1"><Users className="h-3 w-3" /> Together</span>
                  <select value={interaction} onChange={(e) => setInteraction(e.target.value)} className={cn(field, "mt-1")}>
                    <option value="">however the scene reads</option>
                    {Object.entries(lib.interactions).map(([g, items]) => (
                      <optgroup key={g} label={g}>
                        {items.map((i) => <option key={i.id} value={i.id}>{i.id.replace(/-/g, " ")}</option>)}
                      </optgroup>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="block">
                  <span className="text-[10px] text-zinc-500">Pose</span>
                  <input value={pose} onChange={(e) => setPose(e.target.value)}
                    placeholder="how she is arranged" className={cn(field, "mt-1")} />
                </label>
              )}

              <label className="block sm:col-span-2">
                <span className="text-[10px] text-zinc-500">Doing</span>
                <input value={activity} onChange={(e) => setActivity(e.target.value)}
                  placeholder="what is happening" className={cn(field, "mt-1")} />
              </label>

              <label className="block">
                <span className="text-[10px] text-zinc-500">Camera</span>
                <select value={holder} onChange={(e) => setHolder(e.target.value)} className={cn(field, "mt-1")}>
                  <option value="">unspecified</option>
                  {lib.holders.map((h) => <option key={h.id} value={h.id}>{h.id}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] text-zinc-500">Imperfection</span>
                <select value={flaws} onChange={(e) => setFlaws(e.target.value)} className={cn(field, "mt-1")}>
                  <option value="">clean</option>
                  {lib.flaws.map((f) => <option key={f.id} value={f.id}>{f.id}</option>)}
                </select>
              </label>
            </div>
          )}

          {/* THE LEDGER. Every image reference costs identity — measured 0.622 at
              two, 0.579 at three — and every optional one has a text form good
              enough to fall back to. Showing what is actually attached turns an
              invisible tax into a choice. */}
          {ledger.length > 0 && (
            <div className="rounded-lg ring-1 ring-white/8 px-3 py-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {ledger.map((l, i) => (
                  <span key={i} className={cn("rounded-full px-2 py-0.5 text-[10px] ring-1",
                    l.mode === "image" ? "ring-emerald-400/30 text-emerald-300" : "ring-white/10 text-zinc-500")}>
                    {l.mode === "image" ? l.tag : "text"} · {l.label}
                  </span>
                ))}
                {place && (
                  <button onClick={() => setModes((s) => ({ ...s, place: s.place === "image" ? "text" : "image" }))}
                    className="rounded-full px-2 py-0.5 text-[10px] ring-1 ring-white/15 text-zinc-400 hover:text-white">
                    place {modes.place === "image" ? "→ text" : "→ image"}
                  </button>
                )}
              </div>
              <p className="mt-1.5 text-[10px] text-zinc-500">
                {images} image reference{images === 1 ? "" : "s"}
                {images > 2 && " — past two, identity measurably weakens (0.622 at two, 0.579 at three)"}
              </p>
            </div>
          )}
        </div>
      )}

      {err && (
        <div className="mt-3 rounded-lg bg-rose-500/10 ring-1 ring-rose-500/20 px-3 py-2 text-[11px] text-rose-200">
          {err} <button onClick={() => setErr(null)} className="ml-1 underline">dismiss</button>
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button onClick={generate} disabled={!cast.length || !!busy}
          className="rounded-lg bg-white text-black px-5 py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-2">
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> {busy}</> : <><Sparkles className="h-4 w-4" /> Generate scene</>}
        </button>
        {cast.length > 1 && (
          <span className="text-[11px] text-zinc-500">
            owned by {cast[0].name} · everyone sees it in their own review
          </span>
        )}
      </div>

      {result && (
        <div className="mt-4 flex gap-4">
          <img src={`/api/images/${result.file}`} alt="" className="w-48 rounded-lg ring-1 ring-white/10" />
          <div className="text-[11px] space-y-1">
            <div className={cn("font-medium", v?.status === "kept" ? "text-emerald-300" : "text-amber-300")}>{v?.status}</div>
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
            <button onClick={() => setResult(null)} className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 pt-1">
              <X className="h-3 w-3" /> clear
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
