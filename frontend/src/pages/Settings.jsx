import React, { useEffect, useState } from "react";
import { api } from "@/api/throughline";
import { ArrowUp, ArrowDown, Loader2, AlertTriangle } from "lucide-react";
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
