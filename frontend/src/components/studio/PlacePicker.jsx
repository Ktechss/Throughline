import React, { useState } from "react";
import { Home, ImageIcon, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import PlaceUploadModal from "./PlaceUploadModal";

// Location/home gallery — upload place images (named + categorised), pick one to
// anchor the shot's environment as an @image reference.
export default function PlacePicker({ places = [], selected, onSelect, onClear, onSave, onDelete }) {
  const [pending, setPending] = useState(null);
  const [cat, setCat] = useState("All");

  const categories = ["All", ...Array.from(new Set(places.map((p) => p.category || "Uncategorized")))];
  const shown = cat === "All" ? places : places.filter((p) => (p.category || "Uncategorized") === cat);
  const existingCats = Array.from(new Set(places.map((p) => p.category).filter((c) => c && c !== "Uncategorized")));

  const pickFile = (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) setPending(f); };

  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-[12px] font-semibold text-zinc-300 flex items-center gap-1.5">
          <Home className="h-3.5 w-3.5" /> Place
        </h3>
        {selected && <button onClick={onClear} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>}
      </div>
      <p className="text-[10px] text-zinc-600 mb-3">Anchors her environment to this image — a consistent setting, at a small identity cost.</p>

      {categories.length > 1 && (
        <div className="flex flex-wrap gap-1 mb-2 p-1">
          {categories.map((c) => (
            <button key={c} onClick={() => setCat(c)}
              className={cn("rounded-full px-2.5 py-1 text-[10px] whitespace-nowrap ring-1 transition-colors", cat === c ? "bg-white/10 text-white ring-white/15" : "text-zinc-400 ring-white/10 hover:text-zinc-200")}>
              {c}{c !== "All" && <span className="ml-1 text-zinc-500">{places.filter((p) => (p.category || "Uncategorized") === c).length}</span>}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="mb-3 rounded-lg ring-1 ring-white/10 bg-white/[0.03] px-2.5 py-2 text-[11px] font-medium text-zinc-200">
          {selected.name}{selected.category && selected.category !== "Uncategorized" && <span className="ml-2 text-[9px] text-zinc-500">{selected.category}</span>}
        </div>
      )}

      <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(120px,1fr))]">
        <button onClick={() => onClear?.()}
          className={cn("flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-lg ring-1 text-[10px] transition-colors",
            !selected ? "ring-2 ring-emerald-400 bg-emerald-500/10 text-white" : "ring-white/8 text-zinc-500 hover:text-zinc-300 hover:ring-white/25")}>
          <span className="text-base leading-none">∅</span>none
        </button>

        {shown.map((p) => (
          <div key={p.id} title={p.name}
            className={cn("group relative aspect-[4/3] rounded-lg overflow-hidden ring-1 cursor-pointer transition-all",
              selected?.id === p.id ? "ring-2 ring-emerald-400" : "ring-white/8 hover:ring-white/25")}
            onClick={() => onSelect?.(p)}>
            <img src={p.url} alt={p.name} loading="lazy" className="h-full w-full object-cover" />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-1.5 pt-3 pb-1">
              <span className="block truncate text-[9px] text-zinc-100">{p.name}</span>
            </div>
            <button onClick={(e) => { e.stopPropagation(); onDelete?.(p.id); }} title="delete place"
              className="absolute right-1 top-1 rounded bg-black/60 p-1 text-rose-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/85">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}

        <label className="flex aspect-[4/3] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/15 text-[10px] text-zinc-500 hover:border-white/30 hover:text-zinc-300">
          <ImageIcon className="h-4 w-4" /> upload
          <input type="file" accept="image/*" hidden onChange={pickFile} />
        </label>
      </div>
      {places.length === 0 && <p className="mt-2 text-[10px] text-zinc-600">Upload her home/rooms — name and categorise each; pick one to keep the setting consistent.</p>}

      {pending && (
        <PlaceUploadModal
          file={pending} existingCats={existingCats}
          onSave={async (payload) => { await onSave(payload); setPending(null); }}
          onClose={() => setPending(null)}
        />
      )}
    </section>
  );
}
