import React from "react";
import { Sparkles, Loader2, Wand2 } from "lucide-react";
import { cn } from "@/lib/utils";
import VerdictChip from "./VerdictChip";
import OutfitPicker from "./OutfitPicker";
import PosePicker from "./PosePicker";

const RES = ["1K", "2K", "4K"];

export default function ShootTab({
  gens, outfits, poseGroups,
  brief, setBrief, aiPrompt, setAiPrompt, aiBusy, onAiPrompt,
  resolution, setResolution, faceAcc, setFaceAcc,
  selectedOutfit, setSelectedOutfit, selectedPose, setSelectedPose,
  onGenerate, hasIdentity, onOpenDetail, onUploadOutfit, onOpenDesigner,
}) {
  const running = gens.some((g) => g.stage === "running");
  const canGenerate = hasIdentity && (!!brief || !!selectedOutfit || !!selectedPose);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[3fr_2fr] gap-8">
      {/* Left: brief + queue */}
      <div className="space-y-8 min-w-0">
        <section>
          <h2 className="text-[13px] font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-amber-300" /> Shot brief
          </h2>
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={3}
            placeholder="Describe the place, moment, and mood…"
            className="w-full rounded-xl bg-white/[0.03] ring-1 ring-white/10 px-4 py-3 text-[14px] focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
          />

          <div className="mt-3">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[12px] text-zinc-400 flex items-center gap-1.5">
                <Wand2 className="h-3 w-3" /> AI prompt
                <span className="text-[10px] text-zinc-600">Claude-written from brief + outfit + pose</span>
              </label>
              {aiPrompt && <button onClick={() => setAiPrompt("")} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear → template</button>}
            </div>
            <div className="relative">
              <textarea
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                rows={3}
                placeholder="Leave empty to use the template prompt…"
                className="w-full rounded-xl bg-white/[0.02] ring-1 ring-white/10 px-4 py-3 text-[13px] font-mono focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
              />
              <button
                onClick={onAiPrompt}
                disabled={aiBusy || !brief}
                className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-[11px] text-zinc-200 hover:bg-white/20 disabled:opacity-40"
              >
                {aiBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />} {aiBusy ? "Writing…" : "Generate"}
              </button>
            </div>
          </div>

          {/* Controls row */}
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-zinc-500 mr-1">Res</span>
              {RES.map((r) => (
                <button key={r} onClick={() => setResolution(r)} className={cn("rounded-md px-2.5 py-1 text-[11px] ring-1 transition-colors", resolution === r ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{r}</button>
              ))}
            </div>
            <button type="button" onClick={() => setFaceAcc(!faceAcc)} className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
              <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", faceAcc ? "bg-emerald-500/80" : "bg-white/10")}>
                <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", faceAcc ? "translate-x-4" : "translate-x-0")} />
              </span>
              Face accessories
            </button>
          </div>

          {/* Generate button */}
          <button
            onClick={onGenerate}
            disabled={!canGenerate}
            className={cn("mt-5 w-full rounded-xl py-3 text-[14px] font-medium transition-all flex items-center justify-center gap-2",
              canGenerate ? "bg-white text-black hover:bg-zinc-200" : "bg-white/5 text-zinc-600 cursor-not-allowed ring-1 ring-white/5")}
          >
            <Sparkles className="h-4 w-4" /> Generate shot
          </button>
          {!hasIdentity
            ? <p className="mt-2 text-[11px] text-amber-400/80 text-center">No identity reference yet — calibrate her first.</p>
            : !canGenerate && <p className="mt-2 text-[11px] text-zinc-600 text-center">Requires a brief, outfit, or pose.</p>}
        </section>

        {/* Generations queue */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[13px] font-semibold text-zinc-300">Generations queue</h2>
            <span className="text-[11px] text-zinc-600 tabular-nums">{gens.length ? `${gens.length} this session` : ""}{running ? " · working…" : ""}</span>
          </div>
          {gens.length === 0 ? (
            <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.02] py-10 text-center text-[12px] text-zinc-600">
              Fire a shot — each generation lands here as its own card, gated the moment it finishes.
            </div>
          ) : (
            <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(140px,1fr))]">
              {gens.map((g) => <GenerationCard key={g.id} gen={g} onOpen={() => g.raw && onOpenDetail(g)} />)}
            </div>
          )}
        </section>
      </div>

      {/* Right: outfit + pose pickers */}
      <div className="space-y-6 xl:sticky xl:top-6 xl:self-start">
        <OutfitPicker outfits={outfits} selected={selectedOutfit} onSelect={setSelectedOutfit} onClear={() => setSelectedOutfit(null)} onUpload={onUploadOutfit} onOpenDesigner={onOpenDesigner} />
        <PosePicker poses={poseGroups} selected={selectedPose} onSelect={setSelectedPose} onClear={() => setSelectedPose(null)} />
      </div>
    </div>
  );
}

function GenerationCard({ gen, onOpen }) {
  if (gen.stage === "running") {
    return (
      <div className="rounded-lg ring-1 ring-white/8 bg-white/[0.02] overflow-hidden">
        <div className="aspect-square bg-white/[0.02] flex items-center justify-center p-3">
          <div className="text-center">
            <Loader2 className="h-4 w-4 text-amber-300 animate-spin mx-auto mb-1.5" />
            <p className="text-[9px] text-zinc-500 line-clamp-2">{gen.brief}</p>
          </div>
        </div>
        <div className="px-2 py-1.5 flex items-center gap-1">
          <span className="text-[9px] text-zinc-400 truncate">{gen.stageLabel}</span>
          <span className="ml-auto text-[9px] text-zinc-600 tabular-nums">{gen.elapsed}s</span>
        </div>
      </div>
    );
  }

  if (gen.stage === "error") {
    return (
      <div className="rounded-lg ring-1 ring-rose-500/20 bg-rose-500/[0.04] overflow-hidden">
        <div className="aspect-square flex items-center justify-center p-3 text-center">
          <p className="text-[9px] text-rose-300/80 line-clamp-4">{gen.error}</p>
        </div>
        <div className="px-2 py-1.5 text-[9px] text-zinc-500 truncate">{gen.brief}</div>
      </div>
    );
  }

  return (
    <button onClick={onOpen} className="text-left rounded-lg ring-1 ring-white/8 bg-white/[0.02] overflow-hidden hover:ring-white/20 transition-all group">
      <div className="relative aspect-square overflow-hidden bg-zinc-900">
        <img src={gen.thumb} alt={gen.brief} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-1.5">
          <VerdictChip status={gen.status} similarity={gen.similarity} yaw={gen.yaw} facePx={gen.facePx} poseMismatch={gen.poseMismatch} />
        </div>
      </div>
      <div className="px-2 py-1.5">
        <div className="text-[10px] text-zinc-300 line-clamp-1">{gen.brief}</div>
        <div className="mt-0.5 flex items-center gap-1 text-[9px] text-zinc-500">
          <span className="truncate">{gen.model}</span>
          <span>·</span>
          <span className="tabular-nums">{gen.created}</span>
        </div>
      </div>
    </button>
  );
}
