import React, { useState } from "react";
import { Film, Play, Loader2, Clapperboard, Camera, Sparkles, Wand2, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

const MODEL_LABEL = { seedance: "Seedance 1.0 Pro", kling: "Kling 2.1", "happy-horse": "happy-horse" };
const MODEL_NOTE = {
  seedance: "cinematic scene motion · permissive",
  kling: "gentle · most identity-safe",
  "happy-horse": "face-safe · native audio + lip-sync (talking)",
};

export default function VideoTab({
  stills = [],
  videos = [],
  cameraMoves = { moves: [], models: [] },
  wardrobe = [],
  onAnimate,
  onMakeVideo,
  onDirect,
  onGenerateStill,
  videoBusy = null,
  makeBusy = null,
}) {
  const moves = cameraMoves?.moves || [];
  const models = cameraMoves?.models || [];

  const [mode, setMode] = useState("make");

  // --- make-video state ---
  const [scenario, setScenario] = useState("");
  const [outfit, setOutfit] = useState(""); // "" = director picks
  const [length, setLength] = useState(12);

  // --- animate state ---
  const [still, setStill] = useState(null);
  const [sceneDesc, setSceneDesc] = useState("");
  const [model, setModel] = useState("happy-horse");
  const [camera, setCamera] = useState("");
  const [extra, setExtra] = useState("");
  const [directing, setDirecting] = useState(false);

  // director-picks results
  const [note, setNote] = useState("");
  const [imageBrief, setImageBrief] = useState("");
  const [wardrobePick, setWardrobePick] = useState("");
  const [stillBusy, setStillBusy] = useState(false);

  // happy-horse config
  const [dialogue, setDialogue] = useState("");
  const [resolution, setResolution] = useState("1080p");
  const [duration, setDuration] = useState(5);
  const [seed, setSeed] = useState("");
  const [safety, setSafety] = useState(true);
  const [keepAudio, setKeepAudio] = useState(true);

  const selected = stills.find((s) => s.id === still) || null;
  const isHH = model === "happy-horse";
  const effMove = camera || moves[0] || "";

  const direct = async () => {
    if (!sceneDesc.trim() || directing || !onDirect) return;
    setDirecting(true);
    try {
      const p = (await onDirect(sceneDesc.trim())) || {};
      if (p.model) setModel(p.model);
      setDialogue(p.dialogue || "");
      setExtra(p.scene || "");
      if (p.camera_move) setCamera(p.camera_move);
      if (p.duration) setDuration(Number(p.duration));
      if (p.resolution) setResolution(p.resolution);
      setNote(p.note || "");
      setImageBrief(p.image_brief || "");
      setWardrobePick(p.wardrobe || "");
    } catch {
      /* parent surfaces errors */
    } finally {
      setDirecting(false);
    }
  };

  const makeStill = async () => {
    if (!imageBrief.trim() || stillBusy || !onGenerateStill) return;
    setStillBusy(true);
    try {
      const run = await onGenerateStill({ brief: imageBrief.trim(), wardrobe: wardrobePick });
      if (run?.id) setStill(run.id);
    } catch {
      /* parent surfaces errors */
    } finally {
      setStillBusy(false);
    }
  };

  const go = () => {
    if (!selected || videoBusy || !onAnimate) return;
    const file = selected.raw?.file ?? selected.file ?? null;
    const base = {
      run_id: selected.id,
      file,
      camera_move: effMove,
      model,
      extra: extra.trim(),
    };
    const payload = isHH
      ? {
          ...base,
          dialogue: dialogue.trim(),
          resolution,
          duration: Number(duration),
          seed: seed.trim() === "" ? null : Number(seed),
          enable_safety_checker: safety,
          keep_audio: keepAudio,
        }
      : base;
    onAnimate(payload);
  };

  const make = () => {
    if (!scenario.trim() || makeBusy || !onMakeVideo) return;
    onMakeVideo({ scenario: scenario.trim(), wardrobe: outfit || null, duration: Number(length) });
  };

  return (
    <div className="space-y-8">
      {/* Mode toggle */}
      <div className="inline-flex rounded-lg bg-white/5 p-1 ring-1 ring-white/10">
        <button
          onClick={() => setMode("make")}
          className={cn(
            "rounded-md px-4 py-1.5 text-[12px] font-medium transition-colors flex items-center gap-1.5",
            mode === "make" ? "bg-white text-black" : "text-zinc-400"
          )}
        >
          <Clapperboard className="h-3.5 w-3.5" /> Make Video
        </button>
        <button
          onClick={() => setMode("animate")}
          className={cn(
            "rounded-md px-4 py-1.5 text-[12px] font-medium transition-colors flex items-center gap-1.5",
            mode === "animate" ? "bg-white text-black" : "text-zinc-400"
          )}
        >
          <Film className="h-3.5 w-3.5" /> Animate Still
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-8">
        {/* Config panel */}
        <div>
          {mode === "make" ? (
            <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5 space-y-4">
              <h3 className="text-[13px] font-semibold text-zinc-200">Multi-scene from scenario</h3>
              <div>
                <label className="text-[11px] text-zinc-500 mb-1.5 block">Scenario</label>
                <textarea
                  rows={4}
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                  placeholder="Director storyboards into scenes…"
                  className="w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
                />
              </div>
              <div>
                <label className="text-[11px] text-zinc-500 mb-1.5 block">Outfit</label>
                <select
                  value={outfit}
                  onChange={(e) => setOutfit(e.target.value)}
                  className="w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[12px] text-zinc-300 focus:ring-white/30 outline-none"
                >
                  <option value="">auto — director picks</option>
                  {wardrobe.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name || w.id}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <div className="flex justify-between">
                  <label className="text-[11px] text-zinc-500">Length</label>
                  <span className="text-[11px] text-zinc-300 tabular-nums">{length}s</span>
                </div>
                <input
                  type="range"
                  min={6}
                  max={30}
                  value={length}
                  onChange={(e) => setLength(+e.target.value)}
                  className="w-full mt-2 accent-rose-400"
                />
              </div>
              <button
                onClick={make}
                disabled={!scenario.trim() || !!makeBusy}
                className="w-full rounded-lg bg-white text-black py-2.5 text-[13px] font-medium hover:bg-zinc-200 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {makeBusy ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> {makeBusy}
                  </>
                ) : (
                  <>
                    <Clapperboard className="h-4 w-4" /> Make Video
                  </>
                )}
              </button>
              <p className="font-mono text-[10px] text-zinc-600">
                storyboards N scenes → a wardrobe-matched still per scene → animates each → stitches.
              </p>
            </section>
          ) : (
            <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-5 space-y-4">
              <h3 className="text-[13px] font-semibold text-zinc-200">Animate a still</h3>

              {/* pick a still */}
              <div>
                <label className="text-[11px] text-zinc-500 mb-1.5 block">Pick a still (approved)</label>
                {stills.length === 0 ? (
                  <p className="text-[11px] text-zinc-600">
                    No approved shots yet. Generate some in the shoot tab, or approve some in review.
                  </p>
                ) : (
                  <div className="grid grid-cols-4 gap-2">
                    {stills.slice(0, 30).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setStill(s.id)}
                        className={cn(
                          "relative aspect-square rounded-md overflow-hidden ring-1 cursor-pointer group",
                          still === s.id ? "ring-2 ring-rose-400" : "ring-white/8 hover:ring-white/30"
                        )}
                      >
                        <img src={s.thumb} alt="still" className="h-full w-full object-cover" />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                          <Play className="h-4 w-4 text-white" />
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* describe / direct */}
              <div>
                <label className="text-[11px] text-zinc-500 mb-1.5 block">Describe the scene</label>
                <textarea
                  rows={3}
                  value={sceneDesc}
                  onChange={(e) => setSceneDesc(e.target.value)}
                  placeholder="Auto-fills model, dialogue, camera move…"
                  className="w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
                />
                <button
                  onClick={direct}
                  disabled={!sceneDesc.trim() || directing}
                  className="mt-2 rounded-lg ring-1 ring-white/10 bg-white/[0.02] px-3 py-1.5 text-[12px] text-zinc-300 hover:ring-white/30 flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {directing ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> directing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" /> direct this scene
                    </>
                  )}
                </button>
                {note && (
                  <div className="mt-3 flex items-start gap-2 rounded-lg ring-1 ring-white/8 bg-white/[0.02] p-3">
                    <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
                    <p className="text-[11px] text-zinc-400">
                      <span className="text-zinc-200 font-medium">Director's picks:</span> {note}
                    </p>
                  </div>
                )}
                {imageBrief && (
                  <div className="mt-3 rounded-lg ring-1 ring-white/8 bg-white/[0.02] p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-zinc-500">scene still to generate</span>
                      {wardrobePick && (
                        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-300">outfit: {wardrobePick}</span>
                      )}
                    </div>
                    <p className="mt-1.5 text-[11px] text-zinc-400">{imageBrief}</p>
                    <button
                      onClick={makeStill}
                      disabled={stillBusy}
                      className="mt-3 rounded-lg ring-1 ring-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-[12px] text-emerald-300 hover:ring-emerald-500/50 flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {stillBusy ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" /> generating still…
                        </>
                      ) : (
                        <>
                          <Wand2 className="h-3.5 w-3.5" /> generate scene still {wardrobePick ? `(${wardrobePick})` : ""}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* model + camera */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-zinc-500 mb-1.5 block">Model</label>
                  <div className="flex flex-wrap gap-1.5">
                    {models.map((m) => (
                      <button
                        key={m}
                        onClick={() => setModel(m)}
                        title={MODEL_NOTE[m]}
                        className={cn(
                          "rounded-md px-2.5 py-1 text-[11px] ring-1 transition-colors",
                          model === m ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:ring-white/30"
                        )}
                      >
                        {MODEL_LABEL[m] || m}
                      </button>
                    ))}
                  </div>
                  {MODEL_NOTE[model] && <p className="mt-1.5 text-[10px] text-zinc-500">{MODEL_NOTE[model]}</p>}
                </div>
                <div>
                  <label className="text-[11px] text-zinc-500 mb-1.5 block">Camera move</label>
                  <select
                    value={effMove}
                    onChange={(e) => setCamera(e.target.value)}
                    className="w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[12px] text-zinc-300 focus:ring-white/30 outline-none"
                  >
                    {moves.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {isHH && (
                <HappyHorseConfigurator
                  dialogue={dialogue}
                  setDialogue={setDialogue}
                  resolution={resolution}
                  setResolution={setResolution}
                  seed={seed}
                  setSeed={setSeed}
                  duration={duration}
                  setDuration={setDuration}
                  safety={safety}
                  setSafety={setSafety}
                  keepAudio={keepAudio}
                  setKeepAudio={setKeepAudio}
                />
              )}

              <div>
                <input
                  value={extra}
                  onChange={(e) => setExtra(e.target.value)}
                  placeholder="optional: extra motion / scene words"
                  className="w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[13px] focus:ring-white/30 outline-none placeholder:text-zinc-600"
                />
              </div>

              <button
                onClick={go}
                disabled={!selected || !!videoBusy}
                className="w-full rounded-lg bg-white text-black py-2.5 text-[13px] font-medium hover:bg-zinc-200 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {videoBusy ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> {videoBusy}
                  </>
                ) : (
                  <>
                    <Film className="h-4 w-4" /> Generate video
                  </>
                )}
              </button>
              {!selected && <p className="text-[11px] text-zinc-500 text-center">pick a still above first</p>}
            </section>
          )}
        </div>

        {/* Clips list */}
        <div>
          <h3 className="text-[13px] font-semibold text-zinc-200 mb-3">
            Clips <span className="text-zinc-600">({videos.length})</span>
          </h3>
          {videos.length === 0 ? (
            <p className="text-[11px] text-zinc-600">No clips yet.</p>
          ) : (
            <div className="space-y-3">
              {videos.map((v, i) => (
                <ClipCard key={v.id ?? v.file ?? i} clip={v} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HappyHorseConfigurator({
  dialogue,
  setDialogue,
  resolution,
  setResolution,
  seed,
  setSeed,
  duration,
  setDuration,
  safety,
  setSafety,
  keepAudio,
  setKeepAudio,
}) {
  return (
    <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/8 p-3 space-y-3">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-300">
        <MessageSquare className="h-3 w-3" /> happy-horse configurator
      </div>
      <input
        value={dialogue}
        onChange={(e) => setDialogue(e.target.value)}
        placeholder="Dialogue (blank = silent)"
        className="w-full rounded-md bg-white/[0.02] ring-1 ring-white/10 px-2.5 py-1.5 text-[12px] focus:ring-white/30 outline-none placeholder:text-zinc-600"
      />
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <select
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
          className="rounded-md bg-white/[0.02] ring-1 ring-white/10 px-2 py-1.5 text-zinc-300"
        >
          <option value="720p">720p</option>
          <option value="1080p">1080p</option>
        </select>
        <input
          value={seed}
          onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
          placeholder="seed (blank = random)"
          className="rounded-md bg-white/[0.02] ring-1 ring-white/10 px-2 py-1.5 text-zinc-400 placeholder:text-zinc-600"
        />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-[11px] text-zinc-500">Duration</span>
        <span className="text-[11px] text-zinc-300 tabular-nums">{duration}s</span>
      </div>
      <input
        type="range"
        min={3}
        max={15}
        value={duration}
        onChange={(e) => setDuration(+e.target.value)}
        className="w-full accent-rose-400"
      />
      <div className="flex gap-4 text-[11px]">
        <label className="flex items-center gap-1.5 text-zinc-400 cursor-pointer">
          <input type="checkbox" checked={safety} onChange={(e) => setSafety(e.target.checked)} /> safety-checker
        </label>
        <label className="flex items-center gap-1.5 text-zinc-400 cursor-pointer">
          <input type="checkbox" checked={keepAudio} onChange={(e) => setKeepAudio(e.target.checked)} /> keep audio
        </label>
      </div>
    </div>
  );
}

function ClipCard({ clip }) {
  const frames = Array.isArray(clip.frames) ? clip.frames : [];
  const meta = [];
  if (clip.model) meta.push(MODEL_LABEL[clip.model] || clip.model);
  if (clip.camera_move) meta.push(clip.camera_move);
  else if (clip.scenes) meta.push(`${clip.scenes} scenes`);

  return (
    <div className="rounded-xl ring-1 ring-white/8 bg-white/[0.02] overflow-hidden">
      <div className="relative bg-black">
        {clip.file ? (
          <video
            src={`/api/videos/${clip.file}`}
            loop
            controls
            playsInline
            className="w-full aspect-video bg-black object-contain"
          />
        ) : (
          <div className="w-full aspect-video flex items-center justify-center text-[11px] text-zinc-600">
            no video file
          </div>
        )}
        {clip.duration != null && (
          <div className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-zinc-200 tabular-nums pointer-events-none">
            {clip.duration}s
          </div>
        )}
      </div>
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2 text-[11px] text-zinc-400 flex-wrap">
          {meta.map((m, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span>·</span>}
              <span className={i === 0 ? "text-zinc-200" : ""}>{m}</span>
            </React.Fragment>
          ))}
          {clip.dialogue && (
            <>
              <span>·</span>
              <span className="italic text-zinc-500 truncate">“{clip.dialogue}”</span>
            </>
          )}
        </div>

        {/* Per-frame gate results */}
        {frames.length > 0 && (
          <div className="mt-2.5">
            <div className="text-[10px] text-zinc-600 mb-1">per-frame gate</div>
            <div className="flex gap-1">
              {frames.map((f, i) => {
                const status = f.status ?? (f.kept === true ? "kept" : f.kept === false ? "rejected" : undefined);
                const kept = status === "kept";
                const rejected = status === "rejected";
                const sim = typeof f.similarity === "number" ? f.similarity : null;
                const label = f.frame ?? f.idx ?? i;
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                    <div
                      className={cn(
                        "h-8 w-full rounded-sm ring-1",
                        kept
                          ? "bg-emerald-500/30 ring-emerald-500/40"
                          : rejected
                          ? "bg-rose-500/30 ring-rose-500/40"
                          : "bg-amber-500/30 ring-amber-500/40"
                      )}
                      title={`frame ${label} · ${status ?? "pending"}`}
                    />
                    <span className="text-[8px] text-zinc-500 tabular-nums">{sim != null ? sim.toFixed(2) : "—"}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
