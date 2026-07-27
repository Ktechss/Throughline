import React, { useState } from "react";
import { Upload, Star, Loader2, RefreshCw, Lock, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export default function CalibrateTab({
  character,
  bio,
  seed,
  gallery,
  cands = [],
  onGenerateFaces,
  onToggle,
  onAddSelected,
  onSetIdentity,
  onRecalibrate,
  onReset,
  onUploadSeed,
}) {
  const [step, setStep] = useState(2);
  const [faceCount, setFaceCount] = useState(5);
  const [busy, setBusy] = useState(false);

  const selectedCount = cands.filter((c) => c.sel).length;

  const generate = async () => {
    setBusy(true);
    try {
      await onGenerateFaces?.(faceCount);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-4xl">
      {/* Stepper */}
      <div className="flex items-center gap-2 mb-8">
        {["seed", "generate & approve", "lock"].map((label, i) => {
          const n = i + 1;
          const active = step === n;
          const done = step > n;
          return (
            <React.Fragment key={label}>
              <button onClick={() => setStep(n)} className="flex items-center gap-2">
                <span className={cn("h-7 w-7 rounded-full flex items-center justify-center text-[11px] font-semibold ring-1 transition-all", active ? "bg-white text-black ring-white" : done ? "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40" : "ring-white/10 text-zinc-500")}>
                  {done ? <Check className="h-3.5 w-3.5" /> : n}
                </span>
                <span className={cn("text-[12px] font-medium", active ? "text-white" : "text-zinc-500")}>{label}</span>
              </button>
              {i < 2 && <div className="flex-1 h-px bg-white/10 mx-2" />}
            </React.Fragment>
          );
        })}
      </div>

      {step === 1 && <SeedStep bio={bio} seed={seed} onUploadSeed={onUploadSeed} onContinue={() => setStep(2)} />}
      {step === 2 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-[13px] font-semibold text-zinc-200">Generate faces</h3>
              <p className="text-[11px] text-zinc-500 mt-0.5">Click faces to select; add selected to fingerprint, or promote one to identity ★.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <button onClick={() => setFaceCount(Math.max(1, faceCount - 1))} className="h-7 w-7 rounded-md ring-1 ring-white/10 text-zinc-300">−</button>
                <span className="text-[12px] text-zinc-300 w-6 text-center tabular-nums">{faceCount}</span>
                <button onClick={() => setFaceCount(Math.min(12, faceCount + 1))} className="h-7 w-7 rounded-md ring-1 ring-white/10 text-zinc-300">+</button>
              </div>
              <button onClick={generate} disabled={busy} className="rounded-lg bg-white text-black px-4 py-1.5 text-[12px] font-medium hover:bg-zinc-200 disabled:opacity-50 flex items-center gap-1.5">
                <Loader2 className={cn("h-3.5 w-3.5", busy && "animate-spin")} /> {busy ? "Starting…" : "Generate faces"}
              </button>
            </div>
          </div>
          {cands.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {cands.map((c) => (
                <FaceCandidate key={c.jid} cand={c} onToggle={() => onToggle?.(c.jid)} onSetIdentity={() => onSetIdentity?.(c.id)} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl ring-1 ring-white/8 bg-white/[0.02] p-8 text-center text-[12px] text-zinc-500">
              No candidates yet. Set the count and generate faces.
            </div>
          )}
          <div className="mt-5 flex items-center gap-3">
            <button onClick={() => onAddSelected?.()} disabled={selectedCount === 0} className="rounded-lg bg-white/10 hover:bg-white/15 px-4 py-2 text-[12px] text-zinc-200 disabled:opacity-40">Add {selectedCount} to fingerprint</button>
            <button onClick={() => setStep(3)} className="ml-auto rounded-lg ring-1 ring-white/15 px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5">Continue to lock →</button>
          </div>
        </div>
      )}
      {step === 3 && <LockStep gallery={gallery} onRecalibrate={onRecalibrate} onReset={onReset} />}
    </div>
  );
}

function SeedStep({ bio, seed, onUploadSeed, onContinue }) {
  const handleUpload = (e) => {
    const file = e.target.files?.[0];
    if (file) onUploadSeed?.(file);
    e.target.value = "";
  };
  const yaw = seed?.yaw;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-3">Seed face</h3>
        <div className="flex gap-3">
          <div className="relative h-40 w-32 rounded-xl overflow-hidden ring-1 ring-white/10 flex-shrink-0 bg-zinc-900">
            {bio?.calib_seed ? (
              <img src={`/api/refs/${bio.calib_seed}/file`} alt="seed" className="h-full w-full object-cover" />
            ) : (
              <div className="h-full w-full flex items-center justify-center text-[10px] text-zinc-600 text-center px-2">no seed image set</div>
            )}
          </div>
          <div className="text-[12px] space-y-2 min-w-0 flex-1">
            <div className="flex justify-between gap-2"><span className="text-zinc-500">seed name</span><span className="text-zinc-200 truncate">{seed?.name ?? bio?.calib_seed ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">face px</span><span className="text-zinc-200 tabular-nums">{seed?.face_px ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">pose class</span><span className="text-zinc-200">{seed?.pose_class ?? "—"}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">yaw</span><span className="text-zinc-200 tabular-nums">{yaw != null ? `${yaw > 0 ? "+" : ""}${yaw}°` : "—"}</span></div>
          </div>
        </div>
        <label className="mt-4 block rounded-lg border border-dashed border-white/15 p-4 text-center hover:border-white/30 cursor-pointer">
          <Upload className="h-4 w-4 text-zinc-500 mx-auto mb-1.5" />
          <span className="text-[11px] text-zinc-500">Upload base / seed face</span>
          <input type="file" accept="image/*" hidden onChange={handleUpload} />
        </label>
      </section>
      <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-3">Calibration seed</h3>
        <p className="text-[12px] text-zinc-400 leading-relaxed">
          Every calibration face for <span className="text-zinc-200">{character?.name || "this character"}</span> is generated from this seed. Approve the on-model faces to build the identity fingerprint, then lock the threshold.
        </p>
        <p className="mt-3 text-[10px] text-zinc-600">Uploading a seed does not change BIO identity. Set identity later by promoting a generated face (★).</p>
        <button onClick={onContinue} className="mt-4 rounded-lg bg-white text-black px-4 py-2 text-[12px] font-medium hover:bg-zinc-200">Continue →</button>
      </section>
    </div>
  );
}

function FaceCandidate({ cand, onToggle, onSetIdentity }) {
  if (cand.running) {
    return (
      <div className="rounded-xl overflow-hidden ring-1 ring-white/8">
        <div className="relative aspect-square bg-zinc-900 flex flex-col items-center justify-center gap-2 text-center px-2">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
          <span className="text-[10px] text-zinc-400">{cand.stage || "generating…"}</span>
        </div>
        <div className="px-2 py-1.5 flex items-center justify-between text-[9px] text-zinc-500">
          <span>{cand.angle}</span>
        </div>
      </div>
    );
  }
  if (cand.error) {
    return (
      <div className="rounded-xl overflow-hidden ring-1 ring-rose-500/30">
        <div className="relative aspect-square bg-rose-500/5 flex flex-col items-center justify-center gap-1 text-center px-2">
          <span className="text-[11px] text-rose-300">failed</span>
          <span className="text-[9px] text-rose-400/70 break-words">{cand.error}</span>
        </div>
        <div className="px-2 py-1.5 flex items-center justify-between text-[9px] text-zinc-500">
          <span>{cand.angle}</span>
        </div>
      </div>
    );
  }
  return (
    <div className={cn("relative rounded-xl overflow-hidden ring-1 transition-all", cand.sel ? "ring-white" : "ring-white/8 hover:ring-white/20")}>
      <button onClick={onToggle} className="block w-full text-left">
        <div className="relative aspect-square bg-zinc-900">
          <img src={cand.url} alt="candidate" className="h-full w-full object-cover" />
          {cand.sel && <div className="absolute top-1.5 left-1.5 h-5 w-5 rounded-full bg-white text-black flex items-center justify-center"><Check className="h-3 w-3" /></div>}
        </div>
      </button>
      <button onClick={onSetIdentity} title="Use as identity ★" className="absolute top-1.5 right-1.5 h-6 w-6 rounded-full bg-amber-400 text-black flex items-center justify-center hover:bg-amber-300">
        <Star className="h-3 w-3 fill-black" />
      </button>
      <div className="px-2 py-1.5 flex items-center justify-between text-[9px] text-zinc-500">
        <span>{cand.angle}</span>
        <span className="tabular-nums">{cand.yaw != null ? `${cand.yaw > 0 ? "+" : ""}${cand.yaw}°` : "0°"} · {cand.facePx ?? "—"}px</span>
      </div>
    </div>
  );
}

function LockStep({ gallery, onRecalibrate, onReset }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const entries = gallery?.entries || [];
  const threshold = gallery?.threshold;
  const sa = result?.self_agreement || {};

  const recalibrate = async () => {
    setBusy(true);
    try {
      const r = await onRecalibrate?.();
      if (r) setResult(r);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5">
        <div className="flex items-center gap-2 mb-4">
          <Lock className="h-4 w-4 text-emerald-400" />
          <h3 className="text-[13px] font-semibold text-zinc-200">Fingerprint</h3>
        </div>
        <div className="space-y-2.5 text-[12px]">
          <div className="flex justify-between"><span className="text-zinc-500">Fingerprint faces</span><span className="text-zinc-200 tabular-nums">{entries.length}</span></div>
          <div className="flex justify-between"><span className="text-zinc-500">Gate threshold</span><span className="text-zinc-200 tabular-nums">{result?.threshold ?? threshold ?? "—"}</span></div>
          {sa.mean != null && <div className="flex justify-between"><span className="text-zinc-500">Self-agreement mean</span><span className="text-emerald-300 tabular-nums">{sa.mean}</span></div>}
          {sa.min != null && <div className="flex justify-between"><span className="text-zinc-500">Self-agreement min</span><span className="text-amber-300 tabular-nums">{sa.min}</span></div>}
          {result?.faces != null && <div className="flex justify-between"><span className="text-zinc-500">Faces (recalibrated)</span><span className="text-zinc-200 tabular-nums">{result.faces}</span></div>}
        </div>
        <div className="mt-4">
          <div className="text-[11px] text-zinc-500 mb-2">Gallery angle chips</div>
          <div className="flex flex-wrap gap-1.5">
            {entries.length > 0 ? entries.map((a) => (
              <span key={a} className="inline-flex items-center gap-1.5 rounded-full bg-white/5 ring-1 ring-white/10 px-2.5 py-1 text-[10px]">{a}</span>
            )) : <span className="text-[10px] text-zinc-600">No faces in fingerprint yet.</span>}
          </div>
        </div>
      </section>
      <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5 space-y-3">
        <button onClick={recalibrate} disabled={busy || entries.length < 3} className="w-full rounded-lg bg-white/10 hover:bg-white/15 px-4 py-3 text-[12px] text-zinc-200 flex items-center justify-center gap-2 disabled:opacity-40">
          <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} /> Recalibrate threshold
        </button>
        <p className="text-[10px] text-zinc-600 text-center">Needs ≥3 faces in fingerprint.</p>
        <div className="border-t border-white/5 pt-3">
          <button onClick={() => onReset?.()} className="w-full rounded-lg ring-1 ring-rose-500/30 hover:bg-rose-500/10 px-4 py-3 text-[12px] text-rose-300 flex items-center justify-center gap-2">
            <RefreshCw className="h-3.5 w-3.5" /> Reset fingerprint
          </button>
        </div>
      </section>
    </div>
  );
}
