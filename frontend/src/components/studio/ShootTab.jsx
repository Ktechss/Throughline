import React, { useState } from "react";
import { Sparkles, Loader2, Wand2, Shirt, Check, PersonStanding } from "lucide-react";
import { cn } from "@/lib/utils";
import { promptText } from "@/components/ui/confirm";
import { Section } from "@/components/ui/section";
import ModelPicker from "@/components/ModelPicker";
import Picker from "@/components/collab/Picker";
import VerdictChip from "./VerdictChip";
import PickerShelf from "./PickerShelf";
import OutfitPicker from "./OutfitPicker";
import PosePicker from "./PosePicker";
import NailPicker from "./NailPicker";
import { WARDROBE_CATEGORIES } from "@/api/throughline";

const RES = ["1K", "2K", "4K"];

export default function ShootTab({
  gens, outfits, poseGroups,
  brief, setBrief, aiPrompt, setAiPrompt, aiBusy, onAiPrompt,
  resolution, setResolution, faceAcc, setFaceAcc, pov, setPov, bodyRef, setBodyRef,
  aspect, setAspect, shotLib,
  holder, setHolder, flaws, setFlaws, optics, setOptics,
  exposure, setExposure, groomingState, setGroomingState,
  clutter, setClutter,
  safety, setSafety, refBudget, setRefBudget,
  useTimeline, setUseTimeline, shotDate, setShotDate,
  model, setModel,
  withChar, setWithChar, castable = [],
  selectedOutfit, setSelectedOutfit, selectedPose, setSelectedPose,
  onGenerate, shotPreview, hasFace, onOpenDetail, onUploadOutfit, onOpenDesigner, onDeleteOutfit,
  creating, outfitPreview, onSaveOutfit, onDiscardOutfit, outfitCategories = [],
  nails, selectedNail, setSelectedNail, onSaveNail, onDeleteNail,
}) {
  // selectedOutfit / selectedPose / selectedNail hold the picked ROW, not an id
  // — every picker calls onSelect(item) and useStudio reads `.id` off it. These
  // headers used to look the row up BY id, which never matched, so the fallback
  // handed PickerShelf the object itself and React unmounted the tab rendering
  // it as a child. Read the row's fields directly; there is nothing to look up.

  const running = gens.some((g) => g.stage === "running");
  // hasFACE, not hasIdentity: shot() refuses on a missing master reference,
  // which is a different fact from whether she has been calibrated. The two
  // travelled under one prop name and meant opposite things in two files.
  const canGenerate = hasFace && (!!brief || !!selectedOutfit || !!selectedPose);

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
            className="w-full rounded-xl bg-surface ring-1 ring-line px-4 py-3 text-[14px] focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
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
                className="w-full rounded-xl bg-surface ring-1 ring-line px-4 py-3 text-[13px] font-mono focus:ring-white/30 outline-none resize-none placeholder:text-zinc-600"
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
                <button key={r} onClick={() => setResolution(r)} className={cn("rounded-md px-2.5 py-1 text-[11px] ring-1 transition-colors", resolution === r ? "bg-white text-black ring-white" : "ring-line text-zinc-400 hover:text-white")}>{r}</button>
              ))}
            </div>
            <ModelPicker value={model} onChange={setModel} className="w-[248px]" />
            <button type="button" onClick={() => setFaceAcc(!faceAcc)} className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
              <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", faceAcc ? "bg-emerald-500/80" : "bg-white/10")}>
                <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", faceAcc ? "translate-x-4" : "translate-x-0")} />
              </span>
              Face accessories
            </button>
            <button type="button" onClick={() => setPov(!pov)} title="Faceless first-person product/lifestyle shot — anchored on her hand, manicure, outfit and setting"
              className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
              <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", pov ? "bg-emerald-500/80" : "bg-white/10")}>
                <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", pov ? "translate-x-4" : "translate-x-0")} />
              </span>
              POV (faceless)
            </button>
            {/* A wardrobe turnaround compresses her build — four full-body panels
                on one canvas leaves each figure a few hundred pixels tall, and
                bust volume does not survive that. Every saved outfit came back
                slimmer than the body it was generated from. This attaches the
                pinned body reference directly as a third image instead. */}
            <button type="button" onClick={() => setBodyRef(!bodyRef)}
              title="Attach her pinned body reference as a 3rd image so the figure comes from it, not from the outfit sheet. Costs ~0.04 similarity."
              className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
              <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", bodyRef ? "bg-sky-500/80" : "bg-white/10")}>
                <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", bodyRef ? "translate-x-4" : "translate-x-0")} />
              </span>
              Hold her figure
            </button>
          </div>
          {/* THE CAPTURE ROW.
              Every one of these existed on ShotReq and none of them were ever
              sent from this tab — measured across the first 607 runs, `flaws`
              was set 0 times. A control nothing can reach is not a control, and
              the result was 607 photographs with no photographer, taken on no
              particular camera, of a woman who was never less than fully styled.

              Blank means INFERRED, not off: the brief is read for "selfie",
              "imperfect", "just woke up" and so on, and whatever it decides is
              reported back in the preview below. Choosing here overrides it. */}
          {/* SEVEN OPTIONAL OVERRIDES, folded away.
              These were a 7-column grid inside a ~640px column, so every select
              was 91px wide and every value truncated to "from bri…" — a control
              you cannot read is worse than one you cannot see. Blank means
              INFERRED, so the whole group is the definition of progressive
              disclosure: it has a correct default, and the count says how many
              you have overridden without opening it. */}
          {shotLib && !pov && (
            <Section
              className="mt-4"
              title="Camera & finish"
              count={[holder, flaws, optics, exposure, groomingState, clutter].filter(Boolean).length}
              total={6}
              hint={shotPreview?.auto && Object.keys(shotPreview.auto).length
                ? `${Object.keys(shotPreview.auto).length} decided from the brief`
                : "read from the brief"}
            >
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              <Picker auto={shotPreview?.auto?.holder} label="Camera" flat={shotLib.camera_holders?.filter((o) => o.id)}
                value={holder} onChange={setHolder} empty="from brief"
                hint={holder ? undefined : "auto"} />
              <Picker auto={shotPreview?.auto?.flaws} label="Imperfection" flat={shotLib.flaws?.filter((o) => o.id)}
                value={flaws} onChange={setFlaws} empty="from brief" />
              <Picker auto={shotPreview?.auto?.optics} label="Optics" flat={shotLib.optics?.filter((o) => o.id)}
                value={optics} onChange={setOptics} empty="from brief" />
              <Picker label="Exposure" flat={shotLib.exposure?.filter((o) => o.id)}
                value={exposure} onChange={setExposure} empty="clean" />
              <Picker auto={shotPreview?.auto?.grooming_state} label="Her state" flat={shotLib.grooming_state?.filter((o) => o.id)}
                value={groomingState} onChange={setGroomingState} empty="from brief" />
              {/* What is lying around TODAY. Never the room — the corner
                  reference owns that, and a clutter line describing furniture
                  would fight "reproduce that same place faithfully". */}
              <Picker auto={shotPreview?.auto?.clutter} label="Clutter" flat={shotLib.clutter?.filter((o) => o.id)}
                value={clutter} onChange={setClutter} empty="from brief" />
              <Picker label="Frame size" flat={shotLib.aspects}
                value={aspect} onChange={setAspect} empty="3:4" />
            </div>
            </Section>
          )}
          {/* THE THREE OPT-INS.
              Each one was made deliberately per-request by a commit that argued
              the case — "a quiet platform-wide loosening is not a decision that
              belongs in a config constant where nobody sees it" — and then never
              given a control. Across the first 613 runs all three sat at their
              default, so the reasoning was correct and the effect was zero. */}
          {!pov && (
            <div className="mt-3 flex flex-wrap items-end gap-x-5 gap-y-3">
              <label className="block">
                <span className="text-[10px] text-zinc-500">Moderation</span>
                <select value={safety || ""} onChange={(e) => setSafety(e.target.value)}
                  title="fal's own dial. 1 strictest, 6 least strict. Blank uses the provider default (4). Governs OUTPUT moderation — a prompt-level refusal is a policy boundary and this will not move it."
                  className="mt-1 w-[132px] rounded-lg bg-white/5 ring-1 ring-line px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30 text-zinc-200">
                  <option value="">default (4)</option>
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={String(n)}>
                      {n}{n === 1 ? " — strictest" : n === 6 ? " — loosest" : ""}
                    </option>
                  ))}
                </select>
              </label>

              <button type="button" onClick={() => setRefBudget(!refBudget)}
                title="Hold this shot to 2 reference images. Buys ~0.04 similarity and costs the nail / pose / place reference IMAGES — each demoted to its description, and most nails have none. Opt in when identity matters more than the extras."
                className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
                <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", refBudget ? "bg-sky-500/80" : "bg-white/10")}>
                  <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", refBudget ? "translate-x-4" : "translate-x-0")} />
                </span>
                Prioritise identity
              </button>

              <button type="button" onClick={() => setUseTimeline(!useTimeline)}
                title="Let the date show: season light, and a manicure at the right point in its ~2.5 week cycle. Works with no eras set — season and nails come from the date alone."
                className="flex items-center gap-2 text-[12px] text-zinc-400 hover:text-zinc-200">
                <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", useTimeline ? "bg-emerald-500/80" : "bg-white/10")}>
                  <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", useTimeline ? "translate-x-4" : "translate-x-0")} />
                </span>
                Apply the calendar
              </button>

              {useTimeline && (
                <label className="block">
                  <span className="text-[10px] text-zinc-500">Shot date</span>
                  <input type="date" value={shotDate || ""} onChange={(e) => setShotDate(e.target.value)}
                    className="mt-1 rounded-lg bg-white/5 ring-1 ring-line px-2.5 py-1.5 text-[12px] outline-none focus:ring-white/30 text-zinc-200" />
                </label>
              )}
            </div>
          )}
          {pov && <p className="mt-2 text-[11px] text-emerald-300/80">POV mode: no face — describe the product / what's in her hand in the brief. Pick a manicure for best hand consistency. The AI prompt is ignored in POV; identity gate is N/A.</p>}

          {/* WHAT THIS WILL ACTUALLY SEND, before it costs anything.
              Two numbers earn their place. `brief share` is the one a real
              failure turned on: a street brief was 10% of its own prompt and the
              street never rendered — the wardrobe boilerplate did. `face` says
              which side of the 400px plateau the gate will be reading, because
              under it a verdict is about framing rather than identity. */}
          {shotPreview && (
            <div className="mt-4 rounded-xl bg-surface ring-1 ring-line px-3 py-2.5 text-[11px]">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-zinc-400">
                <span>{shotPreview.chars} chars</span>
                <span className={cn(shotPreview.brief_share < 0.15 && "text-amber-400")}>
                  brief {Math.round(shotPreview.brief_share * 100)}%
                </span>
                <span className={cn(shotPreview.face_px < shotPreview.plateau_px && "text-amber-400")}>
                  face ~{shotPreview.face_px}px
                </span>
                <span>{(shotPreview.references || []).length} refs</span>
              </div>
              {shotPreview.brief_share < 0.15 && (
                <p className="mt-1.5 text-amber-400/80">
                  Your brief is a small part of this prompt — the rest is outfit and
                  grooming text, and the model weights what dominates.
                </p>
              )}
              {(shotPreview.references || []).length > 0 && (
                <p className="mt-1.5 text-zinc-500">
                  {shotPreview.references.map((r) => `${r.tag} ${r.file}`).join(" · ")}
                </p>
              )}
              {(shotPreview.demoted || []).map((d) => (
                <p key={d} className="mt-1 text-zinc-500">↓ {d}</p>
              ))}
              {(shotPreview.sanitised || []).map((s, i) => (
                <p key={i} className="mt-1 text-amber-400/70">
                  rewritten: “{s.was}” → “{s.now}” ({s.why})
                </p>
              ))}
              <details className="mt-1.5">
                <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">
                  full prompt
                </summary>
                <p className="mt-1.5 whitespace-pre-wrap text-zinc-400 leading-relaxed max-h-56 overflow-y-auto">
                  {shotPreview.prompt}
                </p>
              </details>
            </div>
          )}

          {/* Generate button */}
          <button
            onClick={onGenerate}
            disabled={!canGenerate}
            className={cn("mt-5 w-full rounded-xl py-3 text-[14px] font-medium transition-all flex items-center justify-center gap-2",
              canGenerate ? "bg-white text-black hover:bg-zinc-200" : "bg-white/5 text-zinc-600 cursor-not-allowed ring-1 ring-white/5")}
          >
            <Sparkles className="h-4 w-4" /> Generate shot
          </button>
          {!hasFace
            ? <p className="mt-2 text-[11px] text-amber-400/80 text-center">No identity reference yet — calibrate her first.</p>
            : !canGenerate && <p className="mt-2 text-[11px] text-zinc-600 text-center">Requires a brief, outfit, or pose.</p>}
        </section>

        {/* Outfit generation — persists here (not in the closable drawer) */}
        {(creating || outfitPreview) && (
          <OutfitGenPanel creating={creating} preview={outfitPreview} categories={outfitCategories} onSave={onSaveOutfit} onDiscard={onDiscardOutfit} />
        )}

        {/* Generations queue */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[13px] font-semibold text-zinc-300">Generations queue</h2>
            <span className="text-[11px] text-zinc-600 tabular-nums">{gens.length ? `${gens.length} this session` : ""}{running ? " · working…" : ""}</span>
          </div>
          {gens.length === 0 ? (
            <div className="rounded-xl ring-1 ring-white/5 bg-surface py-10 text-center text-[12px] text-zinc-600">
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
        {/* WITH — a collaboration. Her face takes @image2, which is the entire
            measured reference budget (2 refs 0.622 vs 3 refs 0.579), so a chosen
            outfit stops being an image and rides as text instead. Said out loud
            here rather than discovered in ref_demoted afterwards. */}
        {castable.length > 0 && (
          <section>
            <div className="flex items-center justify-between">
              <h3 className="text-[12px] font-medium text-zinc-300">With</h3>
              {withChar && (
                <button onClick={() => setWithChar(null)}
                  className="text-[10px] text-zinc-500 hover:text-zinc-300">shoot alone</button>
              )}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {castable.map((c) => (
                <button key={c.id} onClick={() => setWithChar(withChar?.id === c.id ? null : c)}
                  className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors",
                    withChar?.id === c.id ? "bg-white text-black ring-white"
                                          : "ring-line text-zinc-400 hover:text-white")}>{c.name}</button>
              ))}
            </div>
            {withChar && (
              <p className="mt-1.5 text-[10px] text-amber-300/80 leading-relaxed">
                Two faces is the whole reference budget — a chosen outfit will be described
                in words rather than shown, so expect weaker garment detail.
              </p>
            )}
          </section>
        )}

        {/* Outfit leads because it is the first decision on a shoot day; the
            other two open on demand and remember how you left them. */}
        <PickerShelf id="outfit" title="Outfit" icon={Shirt} defaultOpen
          selected={selectedOutfit?.name || selectedOutfit?.id}
          thumb={selectedOutfit?.url}
          onClear={() => setSelectedOutfit(null)}>
          <OutfitPicker outfits={outfits} selected={selectedOutfit} onSelect={setSelectedOutfit} onClear={() => setSelectedOutfit(null)} onUpload={onUploadOutfit} onOpenDesigner={onOpenDesigner} onDelete={onDeleteOutfit} />
        </PickerShelf>

        <PickerShelf id="pose" title="Pose" icon={PersonStanding}
          selected={selectedPose?.label || selectedPose?.id}
          onClear={() => setSelectedPose(null)}>
          <PosePicker poses={poseGroups} selected={selectedPose} onSelect={setSelectedPose} onClear={() => setSelectedPose(null)} />
        </PickerShelf>

        <PickerShelf id="nails" title="Nails" icon={Sparkles}
          selected={selectedNail?.name || selectedNail?.category}
          thumb={selectedNail?.url}
          onClear={() => setSelectedNail(null)}>
          <NailPicker nails={nails} selected={selectedNail} onSelect={setSelectedNail} onClear={() => setSelectedNail(null)} onSave={onSaveNail} onDelete={onDeleteNail} />
        </PickerShelf>
      </div>
    </div>
  );
}

function OutfitGenPanel({ creating, preview, categories, onSave, onDiscard }) {
  const [saveCategory, setSaveCategory] = useState("");
  const allCats = [...new Set([...WARDROBE_CATEGORIES, ...categories])];
  const addCategory = async () => {
    const c = await promptText({ title: "New outfit category",
      placeholder: "e.g. brunch, festive, gym", confirmLabel: "Add" });
    if (c) setSaveCategory(c);
  };

  return (
    <section className="rounded-xl ring-1 ring-line-subtle bg-surface p-4">
      <h2 className="text-[13px] font-semibold text-zinc-300 mb-3 flex items-center gap-2"><Shirt className="h-3.5 w-3.5 text-sky-300" /> Outfit generation</h2>
      {preview ? (
        <div className="flex flex-col sm:flex-row gap-4">
          <img src={`/api/images/${preview.file}`} alt="outfit preview" className="w-40 shrink-0 rounded-lg ring-1 ring-line object-cover" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[12px] text-emerald-300">Generated — save into a category, or discard.</span>
              <button onClick={addCategory} className="text-[11px] text-zinc-500 hover:text-zinc-300">＋ new</button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allCats.map((c) => (
                <button key={c} onClick={() => setSaveCategory(c)}
                  className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors", saveCategory === c ? "bg-white text-black ring-white" : "ring-line text-zinc-400 hover:text-white")}>{c}</button>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => onSave(saveCategory)} disabled={!saveCategory}
                className="rounded-lg bg-white text-black px-4 py-2 text-[12px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-1.5"><Check className="h-3.5 w-3.5" /> Save to wardrobe</button>
              <button onClick={onDiscard} className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5">Discard</button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 text-[13px] text-sky-300">
          <Loader2 className="h-5 w-5 animate-spin" /> {creating} · you can keep working — it lands here when done.
        </div>
      )}
    </section>
  );
}

function GenerationCard({ gen, onOpen }) {
  if (gen.stage === "running") {
    return (
      <div className="rounded-lg ring-1 ring-line-subtle bg-surface overflow-hidden">
        <div className="aspect-square bg-surface flex items-center justify-center p-3">
          <div className="text-center">
            <Loader2 className="h-4 w-4 text-amber-300 animate-spin mx-auto mb-1.5" />
            <p className="text-[11px] text-zinc-500 line-clamp-2">{gen.brief}</p>
          </div>
        </div>
        <div className="px-2 py-1.5 flex items-center gap-1">
          <span className="text-[11px] text-zinc-400 truncate">{gen.stageLabel}</span>
          <span className="ml-auto text-[11px] text-zinc-600 tabular-nums">{gen.elapsed}s</span>
        </div>
      </div>
    );
  }

  if (gen.stage === "error") {
    return (
      <div className="rounded-lg ring-1 ring-rose-500/20 bg-rose-500/[0.04] overflow-hidden">
        <div className="aspect-square flex items-center justify-center p-3 text-center">
          <p className="text-[11px] text-rose-300/80 line-clamp-4">{gen.error}</p>
        </div>
        <div className="px-2 py-1.5 text-[11px] text-zinc-500 truncate">{gen.brief}</div>
      </div>
    );
  }

  return (
    <button onClick={onOpen} className="text-left rounded-lg ring-1 ring-line-subtle bg-surface overflow-hidden hover:ring-white/20 transition-all group">
      <div className="relative aspect-square overflow-hidden bg-zinc-900">
        <img src={gen.thumb} alt={gen.brief} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-1.5">
          <VerdictChip status={gen.status} pov={gen.pov} similarity={gen.similarity} yaw={gen.yaw} facePx={gen.facePx} poseMismatch={gen.poseMismatch} />
        </div>
      </div>
      <div className="px-2 py-1.5">
        <div className="text-[10px] text-zinc-300 line-clamp-1">{gen.brief}</div>
        <div className="mt-0.5 flex items-center gap-1 text-[11px] text-zinc-500">
          <span className="truncate">{gen.model}</span>
          <span>·</span>
          <span className="tabular-nums">{gen.created}</span>
        </div>
      </div>
    </button>
  );
}
