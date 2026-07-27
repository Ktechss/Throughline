import React, { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ShieldCheck, ShieldAlert, Lock, ChevronLeft, Camera, IdCard, Sliders, Film, GalleryHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/api/throughline";
import { useStudio } from "@/api/useStudio";
import ShootTab from "@/components/studio/ShootTab";
import BioTab from "@/components/studio/BioTab";
import CalibrateTab from "@/components/studio/CalibrateTab";
import VideoTab from "@/components/studio/VideoTab";
import ReviewTab from "@/components/studio/ReviewTab";
import ImageDetail from "@/components/studio/ImageDetail";
import OutfitDrawer from "@/components/studio/OutfitDrawer";

const TABS = [
  { id: "shoot", label: "Shoot", icon: Camera },
  { id: "bio", label: "Bio", icon: IdCard },
  { id: "calibrate", label: "Calibrate", icon: Sliders },
  { id: "video", label: "Film", icon: Film },
  { id: "review", label: "Review", icon: GalleryHorizontal },
];

export default function Studio() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "shoot";
  const charParam = params.get("char");
  const [detail, setDetail] = useState(null);

  const s = useStudio(charParam);
  const setTab = (id) => { const n = new URLSearchParams(params); n.set("tab", id); setParams(n); };

  const identityRef = s.bio?.reference ? `/api/refs/${s.bio.reference}/file` : null;
  const angleCount = (s.gallery.entries || []).length;
  const reviewCount = s.shots.length;

  const reviewStats = s.stats && {
    totalShots: s.stats.total,
    keepRate: s.stats.gate?.keep_rate ?? 0,
    approved: s.stats.marks?.approved ?? 0,
    rejected: s.stats.marks?.rejected ?? 0,
    goldSet: s.stats.gold_set ?? 0,
    byPose: (s.stats.by_pose || []).slice(0, 8).map((e) => ({ label: e.key, rate: e.keep_rate, kept: e.kept, total: e.n })),
    byOutfit: (s.stats.by_outfit || []).slice(0, 8).map((e) => ({ label: e.key, rate: e.keep_rate, kept: e.kept, total: e.n })),
  };

  const seed = (s.refs || []).find((r) => r.name === s.bio?.calib_seed) || null;

  // ImageDetail actions
  const toWardrobe = async (id) => {
    const name = window.prompt("Save this outfit to the wardrobe as (category):", "");
    if (!name) return;
    try { await api.send("/api/wardrobe/from-run", "POST", { run_id: id, category: name }); await s.refresh(); }
    catch (e) { s.setErr(String(e)); }
  };
  const toPoseRef = async (id) => {
    const name = window.prompt("Save this as a pose reference named:", "");
    if (!name) return;
    try { await api.send("/api/pose-refs/from-run", "POST", { run_id: id, name }); await s.refresh(); }
    catch (e) { s.setErr(String(e)); }
  };
  const usePose = (run) => {
    const pid = run?.meta?.pose_id;
    if (pid) {
      const found = Object.values(s.poseGroups).flat().find((p) => p.id === pid);
      if (found) s.setSelectedPose(found);
    }
    setDetail(null);
    setTab("shoot");
  };
  const markDetail = (id, decision) => { s.mark(id, decision); setDetail((d) => (d && d.id === id ? { ...d, mark: decision } : d)); };

  return (
    <div className="min-h-screen">
      {/* Bio banner */}
      <div className="border-b border-white/5 bg-gradient-to-b from-white/[0.02] to-transparent">
        <div className="px-6 md:px-10 pt-6">
          <Link to="/" className="inline-flex items-center gap-1.5 text-[12px] text-zinc-500 hover:text-zinc-300 mb-4">
            <ChevronLeft className="h-3.5 w-3.5" /> Switch character
          </Link>
          <button onClick={() => setTab("bio")} className="w-full text-left group">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div className="h-16 w-16 rounded-xl overflow-hidden ring-1 ring-white/10 bg-zinc-800">
                  {identityRef
                    ? <img src={identityRef} alt={s.charName} className="h-full w-full object-cover" />
                    : <div className="h-full w-full flex items-center justify-center text-lg font-semibold text-zinc-600">{(s.charName || "?").slice(0, 2).toUpperCase()}</div>}
                </div>
                {s.hasIdentity && (
                  <div className="absolute -bottom-1.5 -right-1.5 h-6 w-6 rounded-full bg-[#0a0a0b] flex items-center justify-center ring-1 ring-white/15">
                    <Lock className="h-3 w-3 text-emerald-400" />
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-xl font-semibold tracking-tight">{s.charName || "…"}</h1>
                  <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                    s.hasIdentity ? "text-emerald-300 ring-emerald-500/30 bg-emerald-500/10" : "text-amber-300 ring-amber-500/30 bg-amber-500/10")}>
                    {s.hasIdentity ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
                    {s.hasIdentity ? "identity set" : "needs calibration"}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-4 text-[11px] text-zinc-500">
                  {s.bio?.reference && <span>ref · {s.bio.reference}</span>}
                  {s.gallery.threshold != null && <span>threshold <span className="text-zinc-300 tabular-nums">{s.gallery.threshold}</span></span>}
                  <span>{angleCount} gallery angles</span>
                </div>
              </div>
              <div className="hidden md:block text-[11px] text-zinc-500 group-hover:text-zinc-300 transition-colors">view bio →</div>
            </div>
          </button>
        </div>

        {/* Tabs */}
        <div className="sticky top-14 md:top-0 z-20 bg-[#0a0a0b]/90 backdrop-blur-md px-6 md:px-10 mt-5">
          <div className="flex items-center gap-1 border-b border-white/5 overflow-x-auto no-scrollbar">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={cn("relative flex items-center gap-2 px-4 py-3 text-[13px] font-medium transition-colors",
                    active ? "text-white" : "text-zinc-500 hover:text-zinc-300")}>
                  <Icon className="h-4 w-4" strokeWidth={1.5} />
                  {t.label}
                  {t.id === "review" && reviewCount > 0 && <span className="ml-0.5 rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] tabular-nums">{reviewCount}</span>}
                  {active && <span className="absolute inset-x-0 -bottom-px h-0.5 bg-white rounded-full" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {s.err && (
        <div onClick={() => s.setErr(null)} className="mx-6 md:mx-10 mt-4 cursor-pointer rounded-lg ring-1 ring-rose-500/30 bg-rose-500/10 px-4 py-2 text-[12px] text-rose-300">
          {s.err} · dismiss
        </div>
      )}

      <div className="px-6 md:px-10 py-8">
        {s.loading ? (
          <div className="py-24 text-center text-zinc-500 text-[13px]">Loading {s.charName || "character"}…</div>
        ) : (
          <>
            {tab === "shoot" && (
              <ShootTab
                gens={s.gens} outfits={s.wardrobe} poseGroups={s.poseGroups}
                brief={s.brief} setBrief={s.setBrief} aiPrompt={s.aiPrompt} setAiPrompt={s.setAiPrompt}
                aiBusy={s.aiBusy} onAiPrompt={s.onAiPrompt}
                resolution={s.resolution} setResolution={s.setResolution}
                faceAcc={s.faceAcc} setFaceAcc={s.setFaceAcc}
                selectedOutfit={s.selectedOutfit} setSelectedOutfit={s.setSelectedOutfit}
                selectedPose={s.selectedPose} setSelectedPose={s.setSelectedPose}
                onGenerate={s.onGenerate} hasIdentity={!!s.bio?.reference}
                onOpenDetail={setDetail}
                onUploadOutfit={s.uploadOutfit} onOpenDesigner={s.openDesigner}
                creating={s.creating} outfitPreview={s.outfitPreview}
                onSaveOutfit={s.saveOutfit} onDiscardOutfit={s.discardOutfit} outfitCategories={s.outfitCategories}
                nails={s.nails} selectedNail={s.selectedNail} setSelectedNail={s.setSelectedNail}
                onSaveNail={s.saveNail} onDeleteNail={s.deleteNail}
              />
            )}
            {tab === "bio" && (
              <BioTab
                bio={s.bio} gallery={s.gallery} refs={s.refs} bodies={s.bodies} parts={s.parts}
                hasIdentity={s.hasIdentity} bodyPreview={s.bodyPreview} bodyBusy={s.bodyBusy}
                onSetBio={s.setBioRef} onDeleteRef={s.deleteRef} onToGallery={s.toGallery}
                onImport={s.importRef} onUploadRef={s.uploadRef} onSavePart={s.savePart} onResetParts={s.resetParts}
                onUploadShape={s.uploadShape} onCreateBody={s.createBody} onSaveBody={s.saveBody}
                onDiscardBody={s.discardBody} onSelectBody={s.selectBody} onDeleteBody={s.deleteBody}
                home={s.home} homeBusy={s.homeBusy} onSaveHome={s.saveHome}
                onUploadCorner={s.uploadCorner} onGenerateCorner={s.generateCorner} onDeleteCorner={s.deleteCorner}
              />
            )}
            {tab === "calibrate" && (
              <CalibrateTab
                character={{ name: s.charName }} bio={s.bio} seed={seed} gallery={s.gallery} cands={s.calibCands}
                onGenerateFaces={s.generateFaces} onToggle={s.toggleCalib} onAddSelected={s.addCalibToGallery}
                onSetIdentity={s.setCalibIdentity} onRecalibrate={s.recalibrate} onReset={s.resetGallery} onUploadSeed={s.uploadSeed}
              />
            )}
            {tab === "video" && (
              <VideoTab
                stills={s.approvedStills} videos={s.videos} cameraMoves={s.cameraMoves} wardrobe={s.wardrobe}
                onAnimate={s.animate} onMakeVideo={s.makeVideo} onDirect={s.videoDirect} onGenerateStill={s.generateStill}
                videoBusy={s.videoBusy} makeBusy={s.makeBusy}
              />
            )}
            {tab === "review" && (
              <ReviewTab
                stats={reviewStats} shots={s.shots} onOpenDetail={setDetail}
                onMark={s.mark} onDelete={s.deleteRun}
                onExportGold={s.exportGold} onPurgeRejected={s.purgeRejected} onCleanup={s.cleanupImages}
              />
            )}
          </>
        )}
      </div>

      {detail && (
        <ImageDetail
          image={detail} wardrobe={s.wardrobe} onClose={() => setDetail(null)}
          onMark={markDetail} onToWardrobe={toWardrobe} onToPoseRef={toPoseRef} onUsePose={usePose}
        />
      )}

      <OutfitDrawer
        open={s.drawerOpen} onClose={s.closeDesigner} imageUrl={s.outfitImageUrl}
        describing={s.describing} onDescribe={s.describeOutfit}
        outfitText={s.outfitText} setOutfitText={s.setOutfitText} details={s.details} onDetail={s.setDetailField}
        idea={s.idea} setIdea={s.setIdea} pickers={s.pickers} onPicker={s.setPicker}
        enriching={s.enriching} onEnrich={s.enrichOutfit}
        creating={s.creating} onGenerate={s.createOutfit}
        outfitPreview={s.outfitPreview} onSave={s.saveOutfit} onDiscard={s.discardOutfit}
        categories={s.outfitCategories}
      />
    </div>
  );
}
