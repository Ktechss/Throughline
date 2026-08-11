import React, { useState } from "react";
import { X, Loader2, Wand2, Sparkles, ImagePlus, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { DETAIL_FIELDS, OUTFIT_PICKERS, WARDROBE_CATEGORIES } from "@/api/throughline";
import ModelPicker from "@/components/ModelPicker";

// Right-side drawer — the outfit builder. Upload a reference photo (Claude
// describes it) OR type an idea + pick attributes (Claude writes it), then
// review/edit → generate → save into a category.
export default function OutfitDrawer({
  open, onClose, imageUrl,
  describing, onDescribe,
  outfitText, setOutfitText, details, onDetail,
  model, setModel,
  idea, setIdea, pickers, onPicker, enriching, onEnrich,
  creating, onGenerate,
  outfitPreview, onSave, onDiscard, categories = [],
}) {
  const [saveCategory, setSaveCategory] = useState("");
  if (!open) return null;

  const missing = details ? DETAIL_FIELDS.filter((f) => !(details[f.key] || "").trim()).length : 0;
  const allCats = [...new Set([...WARDROBE_CATEGORIES, ...categories])];

  const addCategory = () => {
    const c = window.prompt("New category name:");
    if (c && c.trim()) setSaveCategory(c.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onMouseDown={onClose}>
      <aside className="flex h-full w-full max-w-md flex-col border-l border-white/10 bg-[#0d0d0f]" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-4">
          <h2 className="text-[15px] font-semibold">Outfit designer</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* ---- preview + save ---- */}
          {outfitPreview ? (
            <div>
              <div className="rounded-lg ring-1 ring-emerald-500/25 bg-emerald-500/[0.05] p-3">
                <span className="text-[11px] font-medium text-emerald-300">Generated — save into a category, or discard.</span>
                <img src={`/api/images/${outfitPreview.file}`} alt="outfit preview" className="mt-2 w-full rounded-md ring-1 ring-white/10" />
              </div>
              <div className="mt-4">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] text-zinc-400">Save to category</span>
                  <button onClick={addCategory} className="text-[11px] text-zinc-500 hover:text-zinc-300">＋ new</button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {allCats.map((c) => (
                    <button key={c} onClick={() => setSaveCategory(c)}
                      className={cn("rounded-full px-3 py-1 text-[11px] ring-1 transition-colors", saveCategory === c ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{c}</button>
                  ))}
                </div>
                {saveCategory && <p className="mt-2 text-[11px] text-zinc-500">saves as <span className="text-zinc-300 font-mono">{saveCategory}&lt;n&gt;</span></p>}
              </div>
            </div>
          ) : creating ? (
            <div className="flex items-center gap-3 rounded-lg ring-1 ring-sky-500/30 bg-sky-950/20 p-4">
              <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
              <span className="text-[13px] text-sky-300">{creating} · ~1 min</span>
            </div>
          ) : describing ? (
            <>
              {imageUrl && <img src={imageUrl} alt="uploaded outfit" className="mb-4 max-h-72 w-full rounded-lg ring-1 ring-white/10 object-contain bg-black" />}
              <div className="flex items-center gap-3 rounded-lg ring-1 ring-sky-500/30 bg-sky-950/20 p-4">
                <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
                <span className="text-[13px] text-sky-300">Claude is reading the outfit…</span>
              </div>
            </>
          ) : (
            <>
              {imageUrl && <img src={imageUrl} alt="uploaded outfit" className="mb-4 max-h-72 w-full rounded-lg ring-1 ring-white/10 object-contain bg-black" />}

              {/* 1) upload a photo -> describe */}
              <label className="text-[11px] text-zinc-500">Reference photo — upload an outfit to describe</label>
              <label className="mb-4 mt-1.5 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-white/15 px-3 py-3 text-[12px] text-zinc-400 hover:border-white/30 hover:text-zinc-200">
                <ImagePlus className="h-4 w-4" /> upload an outfit photo
                <input type="file" accept="image/*" hidden onChange={onDescribe} />
              </label>

              {/* 2) editable description */}
              <label className="text-[11px] text-zinc-500">Outfit description — edit freely</label>
              <textarea value={outfitText} onChange={(e) => setOutfitText(e.target.value)} rows={7}
                placeholder="upload a photo above, type an outfit, then Enrich — top, bottom, footwear, accessories"
                className="mb-4 mt-1.5 w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none resize-y leading-relaxed" />

              {/* key details */}
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] text-amber-300">Key details — fill what the photo didn't show</span>
                {missing > 0 && <span className="rounded-full bg-amber-500/15 text-amber-300 px-1.5 py-0.5 text-[10px]">{missing} to add</span>}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {DETAIL_FIELDS.map((f) => {
                  const val = details?.[f.key] || "";
                  const empty = !val.trim();
                  return (
                    <label key={f.key} className="block">
                      <span className="flex items-center gap-1 text-[11px] text-zinc-400">{f.label}{empty && <span className="text-amber-300">• add</span>}</span>
                      <input value={val} onChange={(e) => onDetail(f.key, e.target.value)} placeholder={f.hint}
                        className={cn("mt-1 h-9 w-full rounded-md bg-white/[0.02] px-2.5 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 ring-1 focus:ring-white/30", empty ? "ring-amber-600/40" : "ring-white/10")} />
                    </label>
                  );
                })}
              </div>

              {/* 3) enrich */}
              <div className="my-4 flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-600">
                <span className="h-px flex-1 bg-white/10" /><Sparkles className="h-3 w-3" /> enrich<span className="h-px flex-1 bg-white/10" />
              </div>
              <input value={idea || ""} onChange={(e) => setIdea(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !enriching) onEnrich(); }}
                placeholder="optional tweak — e.g. make it silk · add embroidery · adapt to a sangeet"
                className="mb-3 w-full rounded-lg bg-white/[0.02] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />

              {OUTFIT_PICKERS.map((grp) => (
                <div key={grp.key} className="mb-2.5">
                  <span className="text-[11px] text-zinc-500">{grp.label}</span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {grp.options.map((o) => {
                      const on = pickers?.[grp.key] === o;
                      return (
                        <button key={o} type="button" onClick={() => onPicker(grp.key, on ? "" : o)}
                          className={cn("rounded-full px-2.5 py-1 text-[11px] capitalize ring-1 transition-colors", on ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{o}</button>
                      );
                    })}
                  </div>
                </div>
              ))}

              <button onClick={onEnrich} disabled={enriching}
                className="mt-3 w-full rounded-lg ring-1 ring-sky-500/30 bg-sky-950/20 text-sky-300 hover:border-sky-400 py-2 text-[12px] flex items-center justify-center gap-2 disabled:opacity-50">
                {enriching ? <><Loader2 className="h-4 w-4 animate-spin" /> enriching…</> : <><Sparkles className="h-4 w-4" /> {outfitText.trim() ? "enrich outfit" : "write outfit"}</>}
              </button>
              <p className="mt-2 text-[11px] text-zinc-500">Enrich rewrites the description with richer garment detail — same outfit, adapted by any tweak/attributes.</p>
            </>
          )}
        </div>

        {/* footer */}
        <div className="border-t border-white/5 p-4">
          {outfitPreview ? (
            <div className="flex gap-2">
              <button onClick={() => onSave(saveCategory)} disabled={!saveCategory}
                className="flex-1 rounded-lg bg-white text-black py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center gap-2"><Check className="h-4 w-4" /> Save to wardrobe</button>
              <button onClick={onDiscard} className="rounded-lg ring-1 ring-white/10 px-4 py-2.5 text-[13px] text-zinc-300 hover:bg-white/5">Discard</button>
            </div>
          ) : (
            <>
            <ModelPicker value={model} onChange={setModel} className="mb-3" />
            <button onClick={onGenerate} disabled={describing || !!creating || !outfitText.trim()}
              className="w-full rounded-lg bg-white text-black py-2.5 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center gap-2"><Wand2 className="h-4 w-4" /> Generate outfit</button>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
