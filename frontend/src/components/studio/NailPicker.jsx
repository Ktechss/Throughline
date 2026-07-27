import React, { useState } from "react";
import { Sparkles, ImageIcon, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import NailUploadModal from "./NailUploadModal";

// Manicure gallery — upload nail images (named + categorised via a modal), pick one
// to attach to the shot as an @image reference + its description.
export default function NailPicker({ nails = [], selected, onSelect, onClear, onDescribe, onSave, onDelete }) {
  const [pending, setPending] = useState(null);   // File awaiting the name/category modal
  const [cat, setCat] = useState("All");

  const categories = ["All", ...Array.from(new Set(nails.map((n) => n.category || "Uncategorized")))];
  const shown = cat === "All" ? nails : nails.filter((n) => (n.category || "Uncategorized") === cat);
  const nameCats = Array.from(new Set(nails.map((n) => n.category).filter((c) => c && c !== "Uncategorized")));

  const pickFile = (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) setPending(f); };

  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-[12px] font-semibold text-zinc-300 flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5" /> Nails
        </h3>
        {selected && <button onClick={onClear} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>}
      </div>
      <p className="text-[10px] text-zinc-600 mb-3">Attaches the chosen nail image as a reference — an exact match, at a small identity cost.</p>

      {categories.length > 1 && (
        <div className="flex flex-wrap gap-1 mb-2 p-1">
          {categories.map((c) => (
            <button key={c} onClick={() => setCat(c)}
              className={cn("rounded-full px-2.5 py-1 text-[10px] whitespace-nowrap ring-1 transition-colors", cat === c ? "bg-white/10 text-white ring-white/15" : "text-zinc-400 ring-white/10 hover:text-zinc-200")}>
              {c}{c !== "All" && <span className="ml-1 text-zinc-500">{nails.filter((n) => (n.category || "Uncategorized") === c).length}</span>}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="mb-3 rounded-lg ring-1 ring-white/10 bg-white/[0.03] px-2.5 py-2">
          <div className="text-[11px] font-medium text-zinc-200">{selected.name}{selected.category && selected.category !== "Uncategorized" && <span className="ml-2 text-[9px] text-zinc-500">{selected.category}</span>}</div>
          {selected.description && <div className="text-[10px] text-zinc-500 leading-snug line-clamp-2">{selected.description}</div>}
        </div>
      )}

      <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(72px,1fr))]">
        <button onClick={() => onClear?.()}
          className={cn("flex aspect-square flex-col items-center justify-center gap-1 rounded-lg ring-1 text-[10px] transition-colors",
            !selected ? "ring-white bg-white/10 text-white" : "ring-white/8 text-zinc-500 hover:text-zinc-300 hover:ring-white/20")}>
          <span className="text-base leading-none">∅</span>none
        </button>

        {shown.map((n) => (
          <div key={n.id} title={n.name}
            className={cn("group relative aspect-square rounded-lg overflow-hidden ring-1 cursor-pointer transition-all",
              selected?.id === n.id ? "ring-white" : "ring-white/8 hover:ring-white/20")}
            onClick={() => onSelect?.(n)}>
            <img src={n.url} alt={n.name} loading="lazy" className="h-full w-full object-cover" />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-1 pt-2 pb-0.5">
              <span className="block truncate text-[8px] text-zinc-200">{n.name}</span>
            </div>
            <button onClick={(e) => { e.stopPropagation(); onDelete?.(n.id); }} title="delete nail style"
              className="absolute right-1 top-1 rounded bg-black/60 p-1 text-rose-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/85">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}

        <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/15 text-[10px] text-zinc-500 hover:border-white/30 hover:text-zinc-300">
          <ImageIcon className="h-4 w-4" /> upload
          <input type="file" accept="image/*" hidden onChange={pickFile} />
        </label>
      </div>
      {nails.length === 0 && <p className="mt-2 text-[10px] text-zinc-600">Upload manicure photos you like — name and categorise each; the nails are auto-described.</p>}

      {pending && (
        <NailUploadModal
          file={pending} categories={nameCats}
          onDescribe={onDescribe}
          onSave={async (payload) => { await onSave(payload); setPending(null); }}
          onClose={() => setPending(null)}
        />
      )}
    </section>
  );
}
