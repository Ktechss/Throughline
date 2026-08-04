import React, { useEffect, useRef, useState } from "react";
import { api } from "@/api/throughline";
import { Loader2, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";

// Write the scene, and the CAST falls out of the text. "@kiara and @sonam on a
// rooftop" is a two-hander — which is the right shape for a photograph of
// several people, and why this lives on the landing page rather than inside one
// character's studio.
//
// The cast is resolved SERVER-side (POST /api/scene/cast) even though a regex
// here would look identical. It would not stay identical: the server's parser is
// the one that builds the prompt, and a second copy would eventually disagree
// with it about who is in the scene — which shows up as an outfit on the wrong
// woman, silently.
export default function SceneComposer({ characters, onDone }) {
  const [prompt, setPrompt] = useState("");
  const [cast, setCast] = useState([]);
  const [wardrobe, setWardrobe] = useState({});     // {cid: outfit_id}
  const [closets, setClosets] = useState({});       // {cid: [outfit]}
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);
  const box = useRef(null);

  // Re-resolve as you type, debounced. Cheap (one query) and it keeps the
  // wardrobe rows honest while the sentence is still being written.
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await api.send("/api/scene/cast", "POST", { prompt });
        setCast(r.cast || []);
      } catch { /* mid-sentence is not an error */ }
    }, 300);
    return () => clearTimeout(t);
  }, [prompt]);

  // Each character's own wardrobe, fetched once per character that joins.
  useEffect(() => {
    cast.forEach(async (c) => {
      if (closets[c.id]) return;
      try {
        const r = await fetch("/api/wardrobe", { headers: { "X-Character": c.id } });
        const d = await r.json();
        setClosets((s) => ({ ...s, [c.id]: d.wardrobe || [] }));
      } catch { /* she can still be shot without an outfit */ }
    });
  }, [cast]);

  const insert = (id) => {
    const el = box.current;
    const at = el?.selectionStart ?? prompt.length;
    const next = `${prompt.slice(0, at)}@${id} ${prompt.slice(at)}`;
    setPrompt(next);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + id.length + 2, at + id.length + 2); });
  };

  // Every face costs a slot, and so does every outfit. Shown live, because the
  // identity cost of the fourth reference is real and measured — better read
  // before it is paid than discovered in the verdict.
  const refCount = cast.length + cast.filter((c) => wardrobe[c.id]).length;

  const generate = async () => {
    setErr(null); setResult(null); setBusy("Composing…");
    try {
      const { job } = await api.send("/api/scene", "POST", { prompt, wardrobe });
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await api.get(`/api/jobs/${job}`);
        setBusy(st.stage === "done" ? "Finishing…" : `${st.stage}…`);
        if (st.done) {
          if (st.error) setErr(st.error);
          else setResult(st.run);
          break;
        }
      }
      onDone?.();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  };

  const v = result?.verdict;

  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-[15px] font-semibold tracking-tight">Compose a scene</h2>
        <span className="text-[11px] text-zinc-500">name anyone with @ — the cast follows</span>
      </div>

      <textarea
        ref={box}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        placeholder="@kiara and @sonam on a rooftop at sunset, mid-conversation…"
        className="w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-3 py-2.5 text-[13px] focus:ring-white/30 outline-none resize-none"
      />

      <div className="mt-2 flex flex-wrap gap-1.5">
        {characters.filter((c) => c.has_reference).map((c) => (
          <button key={c.id} onClick={() => insert(c.id)}
            className="rounded-full px-2.5 py-1 text-[11px] ring-1 ring-white/10 text-zinc-400 hover:text-white hover:ring-white/25">
            @{c.id}
          </button>
        ))}
      </div>

      {cast.length > 0 && (
        <div className="mt-4 space-y-2">
          {cast.map((c) => (
            <div key={c.id} className="flex items-center gap-3 rounded-lg ring-1 ring-white/8 px-3 py-2">
              <span className="text-[12px] text-zinc-200 w-28 truncate">{c.name}</span>
              {!c.has_reference ? (
                <span className="text-[11px] text-rose-300">no master face — choose one first</span>
              ) : (
                <select
                  value={wardrobe[c.id] || ""}
                  onChange={(e) => setWardrobe((w) => ({ ...w, [c.id]: e.target.value || undefined }))}
                  className="flex-1 rounded-md bg-white/5 ring-1 ring-white/10 px-2 py-1.5 text-[12px] outline-none">
                  <option value="">no outfit — describe it in the scene</option>
                  {(closets[c.id] || []).map((o) => (
                    <option key={o.id} value={o.id}>{o.id}{o.category ? ` · ${o.category}` : ""}</option>
                  ))}
                </select>
              )}
            </div>
          ))}

          <p className="text-[10px] text-zinc-500 leading-relaxed">
            {refCount} reference{refCount === 1 ? "" : "s"} — each face and each outfit takes one.
            {refCount > 2 && " Past two, identity measurably weakens (0.622 at two, 0.579 at three): exact garments, softer faces."}
          </p>
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
            <div className={cn("font-medium", v?.status === "kept" ? "text-emerald-300" : "text-amber-300")}>
              {v?.status}
            </div>
            {(v?.cast || []).map((m) => (
              <div key={m.character} className="text-zinc-400">
                {m.character}: {m.similarity} · {m.face_px}px · yaw {m.yaw}
              </div>
            ))}
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
