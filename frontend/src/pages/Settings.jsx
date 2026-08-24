import React, { useEffect, useState } from "react";
import { api } from "@/api/throughline";
import { ArrowUp, ArrowDown, Loader2, AlertTriangle, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useModels } from "@/components/ModelPicker";

// PROVIDERS — who renders, in what order.
//
// All three resell Google's nano-banana-pro, so this is a price and latency
// decision, not a quality one. Measured on one prompt, three references, 4K,
// scored on her own gallery — the provider was the only variable:
//
//     fal    0.4304   $0.30            66s
//     kie    0.4267   $0.12 (24 cr)   220s
//     poyo   0.4426   $0.175 (35 cr)  265s
//
// 0.016 of spread against seed-to-seed variance of 0.12-0.63 on identical
// prompts. The list is walked top-down and the first one that answers renders
// the shot; a failure costs latency, never the generation.

export default function Settings() {
  const { models, def, saveDefault } = useModels();
  const [modelErr, setModelErr] = useState(null);
  const [rows, setRows] = useState([]);
  const [chain, setChain] = useState([]);
  const [credits, setCredits] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  // Eras. The backend has had GET/PUT /api/timeline since the timeline shipped
  // and nothing ever called them, so every character's era list is [] — which is
  // why `use_timeline` produced season and manicure but never a haircut.
  const [tl, setTl] = useState(null);
  const [eraBusy, setEraBusy] = useState(false);

  const loadTl = () => api.get("/api/timeline").then(setTl).catch(() => {});
  useEffect(() => { loadTl(); }, []);

  const saveEras = async (eras) => {
    setTl((t) => ({ ...(t || {}), eras }));       // optimistic
    setEraBusy(true); setErr(null);
    try { await api.send("/api/timeline", "PUT", { eras }); await loadTl(); }
    catch (e) { setErr(String(e)); await loadTl(); }
    finally { setEraBusy(false); }
  };

  const eras = tl?.eras || [];
  const patchEra = (i, k, v) =>
    saveEras(eras.map((e, j) => (j === i ? { ...e, [k]: v } : e)));

  const load = () =>
    api.get("/api/providers")
       .then((d) => { setRows(d.providers || []); setChain(d.chain || []); setCredits(d.kie_credits); })
       .catch((e) => setErr(String(e)));

  useEffect(() => { load(); }, []);

  const persist = async (next) => {
    setRows(next);                      // optimistic — the list is the control
    setBusy(true); setErr(null);
    try {
      const d = await api.send("/api/providers", "PUT",
        { order: next.map(({ name, enabled }) => ({ name, enabled })) });
      setRows(d.providers || next); setChain(d.chain || []);
    } catch (e) { setErr(String(e)); load(); }
    finally { setBusy(false); }
  };

  const move = (i, by) => {
    const next = [...rows];
    const j = i + by;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    persist(next);
  };

  const toggle = (i) =>
    persist(rows.map((r, k) => (k === i ? { ...r, enabled: !r.enabled } : r)));

  // What the top of the chain costs, versus always using the dearest.
  const first = rows.find((r) => r.enabled && r.has_key);
  const fal = rows.find((r) => r.name === "fal");
  const saving = first && fal && first.usd < fal.usd
    ? Math.round((1 - first.usd / fal.usd) * 100) : 0;

  return (
    <div className="px-5 md:px-8 py-7 max-w-[900px] mx-auto">
      <div className="mb-6">
        <h1 className="text-[19px] font-semibold tracking-tight">Settings</h1>
        <p className="text-[12px] text-zinc-500 mt-0.5">
          Who renders your shots, and in what order.
        </p>
      </div>

      {err && (
        <div className="mb-4 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 px-3 py-2 text-[12px] text-rose-300">
          {err}
        </div>
      )}

      {/* ERAS — the calendar's slow axis.
          Season and manicure fall out of the date on their own; an era is the
          part that needs a human, because it says she got a haircut. The API has
          existed since the timeline shipped and nothing called it, so every
          character's list is empty and "Apply the calendar" has never been able
          to age her hair. */}
      <section className="mb-9">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-[13px] font-semibold text-zinc-300">Eras</h2>
          {eraBusy && <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-500" />}
        </div>
        <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
          Hair moves in slow steps, and continuity across them is what makes two
          photographs six months apart read as one person living rather than two
          attempts at the same prompt. An era starts on its date and runs until
          the next one.
          {tl?.preview && (
            <><br /><span className="text-zinc-600">Today: {tl.preview}</span></>
          )}
        </p>

        <div className="space-y-2">
          {eras.map((e, i) => (
            <div key={i} className="rounded-xl bg-white/[0.03] ring-1 ring-white/10 p-3">
              <div className="flex flex-wrap items-end gap-3">
                <label className="block">
                  <span className="text-[10px] text-zinc-500">From</span>
                  <input type="date" value={e.from || ""}
                    onChange={(ev) => patchEra(i, "from", ev.target.value)}
                    className="mt-1 block rounded-lg bg-white/5 ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30 text-zinc-200" />
                </label>
                <label className="block flex-1 min-w-[10rem]">
                  <span className="text-[10px] text-zinc-500">Name</span>
                  <input value={e.name || ""} placeholder="long hair, pre-monsoon"
                    onChange={(ev) => patchEra(i, "name", ev.target.value)}
                    className="mt-1 block w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30 text-zinc-200 placeholder:text-zinc-600" />
                </label>
                <button onClick={() => saveEras(eras.filter((_, j) => j !== i))}
                  title="Remove this era"
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-rose-300 hover:bg-white/5">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>

              <label className="block mt-2">
                <span className="text-[10px] text-zinc-500">Hair</span>
                <input value={e.hair || ""} placeholder="cut to the collarbone, blunt ends"
                  onChange={(ev) => patchEra(i, "hair", ev.target.value)}
                  className="mt-1 block w-full rounded-lg bg-white/5 ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30 text-zinc-200 placeholder:text-zinc-600" />
              </label>

              {/* Off by default and deliberately so: an era's hair line DESCRIBES
                  her, which is the one thing the pipeline otherwise refuses to do
                  over a reference (0.834 described vs 0.860 terse). Overriding the
                  reference is the whole point when she has had a haircut the
                  reference predates — but it is a decision with a measured cost,
                  never a default. */}
              <button onClick={() => patchEra(i, "apply_hair", !e.apply_hair)}
                disabled={!(e.hair || "").trim()}
                title="Let this era's hair line override the reference. It describes her, which costs identity (0.834 vs 0.860 measured) — turn on only when she has had a haircut the reference predates."
                className={cn("mt-2 flex items-center gap-2 text-[11px]",
                  (e.hair || "").trim() ? "text-zinc-400 hover:text-zinc-200" : "text-zinc-600 cursor-not-allowed")}>
                <span className={cn("relative inline-flex h-4 w-8 shrink-0 rounded-full transition-colors",
                  e.apply_hair ? "bg-amber-500/80" : "bg-white/10")}>
                  <span className={cn("absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                    e.apply_hair ? "translate-x-4" : "translate-x-0")} />
                </span>
                Override the reference&rsquo;s hair &middot; costs ~0.03 identity
              </button>
            </div>
          ))}
        </div>

        <button
          onClick={() => saveEras([...eras, { from: new Date().toISOString().slice(0, 10), name: "" }])}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg ring-1 ring-white/10 px-3 py-1.5 text-[12px] text-zinc-300 hover:ring-white/30">
          <Plus className="h-3.5 w-3.5" /> Add an era
        </button>
        {!eras.length && (
          <p className="mt-2 text-[11px] text-zinc-600">
            No eras yet. Season and manicure still apply from the date alone &mdash;
            an era only adds the haircut.
          </p>
        )}
      </section>

      <section className="mb-9">
        <h2 className="text-[13px] font-semibold text-zinc-300 mb-2">Default model</h2>
        <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
          What renders when a generation does not pick its own. Every Shoot, outfit
          and scene has its own picker that overrides this for one image, so the
          wardrobe can be made on one model and the shot that wears it on another.
        </p>
        <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
          Measured on one project prompt, same references, scored on her own gallery:
          nano-banana-pro <span className="tabular-nums text-zinc-300">0.7634</span>,
          seedream-4.5 <span className="tabular-nums text-zinc-300">0.7724</span>,
          5-pro <span className="tabular-nums text-zinc-300">0.7638</span>,
          5-lite <span className="tabular-nums text-zinc-300">0.6658</span>. Identity is
          close across all four — photorealism is not. Nano renders skin texture and
          hand anatomy the seedream tiers do not, and the gate is blind to both, so
          these numbers do not rank them the way your eye will.
        </p>

        {modelErr && (
          <div className="mb-3 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 px-3 py-2 text-[12px] text-rose-300">
            {modelErr}
          </div>
        )}

        <div className="space-y-2">
          {models.map((m) => (
            <button key={m.id}
              onClick={() => { setModelErr(null); saveDefault(m.id).catch((e) => setModelErr(String(e))); }}
              className={cn("w-full text-left rounded-xl ring-1 px-3 py-2.5 transition-colors",
                m.id === def ? "bg-emerald-500/[0.08] ring-emerald-500/40" : "bg-white/[0.02] ring-white/10 hover:bg-white/[0.04]")}>
              <div className="flex items-center gap-2">
                <span className={cn("text-[13px]", m.id === def ? "text-zinc-100" : "text-zinc-300")}>{m.label}</span>
                {m.id === def && (
                  <span className="rounded-md bg-emerald-500/15 text-emerald-300 px-1.5 py-0.5 text-[10px]">default</span>
                )}
                {m.ceiling !== "4K" && (
                  <span className="rounded-md bg-amber-500/15 text-amber-300 px-1.5 py-0.5 text-[10px]">
                    {m.ceiling} max
                  </span>
                )}
                <span className="ml-auto text-[11px] text-zinc-500 tabular-nums">${m.usd_4k.toFixed(3)}/4K</span>
              </div>
              <div className="text-[11px] text-zinc-500 mt-0.5 tabular-nums">
                {m.model} · up to {m.max_refs} references
              </div>
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-[13px] font-semibold text-zinc-300">Image providers</h2>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-500" />}
        </div>
        <p className="text-[11px] text-zinc-500 mb-3 leading-relaxed">
          All three resell the same Google model — measured at 0.4304 / 0.4267 / 0.4426
          on one prompt, which is inside the variance two identical prompts show. So this
          is a price and speed choice, not a quality one. The list is tried top-down and
          the first that answers renders the shot.
        </p>

        <div className="space-y-2">
          {rows.map((r, i) => {
            const live = chain[0] === r.name;
            const dead = !r.has_key;
            return (
              <div key={r.name}
                className={cn("rounded-xl ring-1 px-3 py-2.5 flex items-center gap-3",
                  r.enabled && !dead ? "bg-white/[0.03] ring-white/10" : "bg-white/[0.01] ring-white/5")}>
                <div className="flex flex-col gap-0.5">
                  <button onClick={() => move(i, -1)} disabled={i === 0}
                    className="text-zinc-500 hover:text-zinc-200 disabled:opacity-20">
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => move(i, 1)} disabled={i === rows.length - 1}
                    className="text-zinc-500 hover:text-zinc-200 disabled:opacity-20">
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={cn("text-[13px]", r.enabled && !dead ? "text-zinc-100" : "text-zinc-500")}>
                      {r.label}
                    </span>
                    {live && (
                      <span className="rounded-md bg-emerald-500/15 text-emerald-300 px-1.5 py-0.5 text-[10px]">
                        in use
                      </span>
                    )}
                    {dead && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 text-amber-300 px-1.5 py-0.5 text-[10px]">
                        <AlertTriangle className="h-3 w-3" /> no {r.key_env}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">
                    ${r.usd.toFixed(3)}/4K · ~{r.seconds}s · {r.note}
                  </div>
                </div>

                <button onClick={() => toggle(i)} disabled={dead}
                  title={dead ? `Add ${r.key_env} to .env first` : "Enable / disable"}
                  className="shrink-0 disabled:opacity-30">
                  <span className={cn("relative inline-flex h-5 w-9 rounded-full transition-colors",
                    r.enabled && !dead ? "bg-emerald-500/80" : "bg-white/10")}>
                    <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      r.enabled && !dead ? "translate-x-4" : "translate-x-0")} />
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        <div className="mt-3 text-[11px] text-zinc-500 space-y-1">
          <p>
            Order in use: <span className="text-zinc-300">{chain.join(" → ") || "—"}</span>
            {saving > 0 && <span className="text-emerald-400"> · {saving}% under fal per shot</span>}
          </p>
          {typeof credits === "number" && (
            <p className={cn(credits < 24 && "text-amber-400")}>
              kie balance {credits} credits — {Math.floor(credits / 24)} more 4K shots at 24 each.
              {credits < 24 && " Too low to render; shots will fall through to the next provider."}
            </p>
          )}
          <p>
            poyo has no uploader of its own, so it hosts references on kie — it needs a
            KIE_API_KEY even when kie itself is switched off.
          </p>
          <p>
            Disabling everything falls back to fal rather than leaving nothing able to
            render.
          </p>
        </div>
      </section>
    </div>
  );
}
