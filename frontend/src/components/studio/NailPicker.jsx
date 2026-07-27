import { Sparkles, ImageIcon, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

// Manicure gallery — upload nail images, pick one to attach to the shot (as an
// extra @image reference + its description). Identity trade is opt-in per shot.
export default function NailPicker({ nails = [], selected, onSelect, onClear, onUpload, onDelete }) {
  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-[12px] font-semibold text-zinc-300 flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5" /> Nails
        </h3>
        {selected && <button onClick={onClear} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>}
      </div>
      <p className="text-[10px] text-zinc-600 mb-3">Attaches the chosen nail image as a reference — an exact match, at a small identity cost.</p>

      {selected?.description && (
        <div className="mb-3 rounded-lg ring-1 ring-white/10 bg-white/[0.03] px-2.5 py-2 text-[10px] text-zinc-400 leading-snug line-clamp-3">
          {selected.description}
        </div>
      )}

      <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(72px,1fr))]">
        <button onClick={() => onClear?.()}
          className={cn("flex aspect-square flex-col items-center justify-center gap-1 rounded-lg ring-1 text-[10px] transition-colors",
            !selected ? "ring-white bg-white/10 text-white" : "ring-white/8 text-zinc-500 hover:text-zinc-300 hover:ring-white/20")}>
          <span className="text-base leading-none">∅</span>none
        </button>

        {nails.map((n) => (
          <div key={n.id}
            className={cn("group relative aspect-square rounded-lg overflow-hidden ring-1 cursor-pointer transition-all",
              selected?.id === n.id ? "ring-white" : "ring-white/8 hover:ring-white/20")}
            onClick={() => onSelect?.(n)}>
            <img src={n.url} alt={n.id} loading="lazy" className="h-full w-full object-cover" />
            <button onClick={(e) => { e.stopPropagation(); onDelete?.(n.id); }} title="delete nail style"
              className="absolute right-1 top-1 rounded bg-black/60 p-1 text-rose-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/85">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}

        <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/15 text-[10px] text-zinc-500 hover:border-white/30 hover:text-zinc-300">
          <ImageIcon className="h-4 w-4" /> upload
          <input type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onUpload?.(f); }} />
        </label>
      </div>
      {nails.length === 0 && <p className="mt-2 text-[10px] text-zinc-600">Upload manicure photos you like — each is auto-described and becomes a preset.</p>}
    </section>
  );
}
