import React, { useMemo, useRef, useState } from "react";
import { Upload, Link2, Wand2, Loader2, Play, Shirt, Video } from "lucide-react";
import { cn } from "@/lib/utils";

// Pose-driven motion transfer (wan-motion): a driving video + a gate-checked
// still of HER -> her performing that motion. Identity comes from the still; the
// driver contributes only pose, so the source person never bleeds in.
const RATE = 0.06; // $/sec @720p

export default function MotionTab({
  videos = [],
  wardrobe = [],
  onUploadDriver,
  onUploadDriverUrl,
  onGenerateStill,
  onRunMotion,
  motionBusy = null,
}) {
  const fileRef = useRef(null);
  const [driver, setDriver] = useState(null);     // {driver, first_frame, duration, w, h}
  const [driverBusy, setDriverBusy] = useState(false);
  const [url, setUrl] = useState("");

  const [outfit, setOutfit] = useState("");
  const [brief, setBrief] = useState(
    "Waist-up portrait, facing straight forward at the camera, her face large and clearly visible, natural pose, no eyewear.");
  const [genBusy, setGenBusy] = useState(false);
  const [still, setStill] = useState(null);        // {file, similarity, status}

  const [maxSeconds, setMaxSeconds] = useState(6);
  const [prompt, setPrompt] = useState("Preserve her exact facial identity from the reference image.");

  const results = useMemo(() => (videos || []).filter((v) => v.model === "wan-motion"), [videos]);
  const cost = (Math.min(maxSeconds, driver?.duration || maxSeconds) * RATE).toFixed(2);
  const ready = driver && still && !motionBusy;

  const pickFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setDriverBusy(true); setDriver(null);
    try { setDriver(await onUploadDriver(f)); } finally { setDriverBusy(false); }
  };
  const fetchUrl = async () => {
    if (!url.trim()) return;
    setDriverBusy(true); setDriver(null);
    try { setDriver(await onUploadDriverUrl(url.trim())); } finally { setDriverBusy(false); }
  };
  const genStill = async () => {
    setGenBusy(true); setStill(null);
    try {
      const run = await onGenerateStill({ brief, wardrobe: outfit });
      if (run) setStill({ file: run.file, similarity: run.verdict?.similarity, status: run.verdict?.status });
    } finally { setGenBusy(false); }
  };
  const send = async () => {
    if (!ready) return;
    await onRunMotion({ still: still.file, driver: driver.driver, prompt, max_seconds: Number(maxSeconds) || null });
  };

  const step = "rounded-xl border border-white/10 bg-white/[0.02] p-4";
  const head = "flex items-center gap-2 text-sm font-medium text-zinc-200";

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* LEFT: driving video */}
      <div className={step}>
        <div className={head}><Video className="h-4 w-4" /> 1 · Driving video</div>
        <p className="mt-1 text-xs text-zinc-500">The motion to copy. Only its pose is used — the source face never enters.</p>

        <div className="mt-3 flex gap-2">
          <button onClick={() => fileRef.current?.click()} disabled={driverBusy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-zinc-100 hover:bg-white/15 disabled:opacity-50">
            {driverBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload
          </button>
          <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={pickFile} />
        </div>
        <div className="mt-2 flex gap-2">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="…or paste a video URL"
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600" />
          <button onClick={fetchUrl} disabled={driverBusy || !url.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/15 disabled:opacity-50">
            <Link2 className="h-4 w-4" /> Fetch
          </button>
        </div>
        <p className="mt-1 text-[11px] text-zinc-600">Pinterest/TikTok URLs are often JS-gated — if Fetch fails, download and upload.</p>

        {driver && (
          <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
            {driver.first_frame && <img src={driver.first_frame} alt="first frame" className="w-full object-cover" />}
            <div className="bg-black/40 px-2 py-1 text-[11px] text-zinc-400">
              {driver.w}×{driver.h} · {driver.duration}s · <span className="text-zinc-500">{driver.driver}</span>
            </div>
          </div>
        )}
      </div>

      {/* RIGHT: outfit -> still */}
      <div className={step}>
        <div className={head}><Shirt className="h-4 w-4" /> 2 · Her outfit</div>
        <p className="mt-1 text-xs text-zinc-500">Generate a gate-checked still of her in an outfit — this anchors identity.</p>

        <select value={outfit} onChange={(e) => setOutfit(e.target.value)}
          className="mt-3 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-zinc-200">
          <option value="">— pick an outfit —</option>
          {(wardrobe || []).map((w) => <option key={w.id} value={w.id}>{w.id}</option>)}
        </select>
        <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={2}
          className="mt-2 w-full resize-none rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-zinc-300" />
        <button onClick={genStill} disabled={genBusy || !outfit}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/15 disabled:opacity-50">
          {genBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} Generate still
        </button>

        {still && (
          <div className="mt-3 flex gap-3">
            <img src={`/api/images/${still.file}/thumb`} alt="still" className="h-28 w-auto rounded-lg border border-white/10" />
            <div className="text-xs">
              <div className="text-zinc-400">gate similarity</div>
              <div className={cn("text-2xl font-semibold tabular-nums",
                (still.similarity ?? 0) >= 0.5 ? "text-emerald-400" : "text-amber-400")}>
                {still.similarity != null ? still.similarity.toFixed(3) : "—"}
              </div>
              <div className="text-zinc-600">{still.status}</div>
            </div>
          </div>
        )}
      </div>

      {/* FULL WIDTH: send + result */}
      <div className={cn(step, "lg:col-span-2")}>
        <div className={head}><Play className="h-4 w-4" /> 3 · Transfer motion (wan-motion)</div>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            max seconds
            <input type="number" min={2} max={15} value={maxSeconds} onChange={(e) => setMaxSeconds(e.target.value)}
              className="w-16 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm text-zinc-200" />
          </label>
          <span className="text-xs text-zinc-500">≈ ${cost} @720p</span>
          <input value={prompt} onChange={(e) => setPrompt(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-zinc-300" />
          <button onClick={send} disabled={!ready}
            className={cn("inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium",
              ready ? "bg-emerald-500/90 text-black hover:bg-emerald-400" : "bg-white/10 text-zinc-500")}>
            {motionBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {motionBusy ? String(motionBusy) : "Send to wan-motion"}
          </button>
        </div>
        {!driver && <p className="mt-2 text-[11px] text-amber-400/80">Add a driving video first.</p>}
        {driver && !still && <p className="mt-2 text-[11px] text-amber-400/80">Generate her still first.</p>}

        {results.length > 0 && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((v) => {
              const sims = (v.frames || []).map((f) => f.similarity).filter((x) => x != null);
              const mean = sims.length ? (sims.reduce((a, b) => a + b, 0) / sims.length) : null;
              return (
                <div key={v.id} className="overflow-hidden rounded-lg border border-white/10 bg-black/20">
                  <video src={`/api/videos/${v.file}`} controls className="w-full" />
                  <div className="flex items-center justify-between px-2 py-1 text-[11px] text-zinc-400">
                    <span>{v.created?.replace("T", " ")}</span>
                    {mean != null && <span className={cn("tabular-nums", mean >= 0.5 ? "text-emerald-400" : "text-amber-400")}>
                      gate {mean.toFixed(2)}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
