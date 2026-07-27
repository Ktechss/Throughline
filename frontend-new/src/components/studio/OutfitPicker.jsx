import { Shirt, ImageIcon, Wand2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAssetBrowser } from "./useAssetBrowser";
import { SearchBox, CategoryChips, CountLine, EmptyState } from "./assetBrowserParts";

export default function OutfitPicker({ outfits, selected, onSelect, onClear, onUpload, onOpenDesigner }) {
  const categories = ["All", ...Array.from(new Set(outfits.map((o) => o.category)))];
  const browser = useAssetBrowser({ items: outfits, categories, pageSize: 12 });

  return (
    <section className="rounded-2xl ring-1 ring-white/8 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[12px] font-semibold text-zinc-300 flex items-center gap-1.5">
          <Shirt className="h-3.5 w-3.5" /> Outfit
        </h3>
        {selected && (
          <button onClick={onClear} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>
        )}
      </div>

      <SearchBox value={browser.query} onChange={browser.setQuery} placeholder="Search outfits…" />
      <CategoryChips categories={categories} active={browser.category} onSelect={browser.setCategory} />
      <CountLine visible={browser.visible.length} total={browser.total} />

      <div className="mt-2 max-h-[360px] overflow-y-auto pr-1">
        <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(90px,1fr))]">
          {browser.visible.map((o) => (
            <button
              key={o.id}
              onClick={() => onSelect(o)}
              className={cn(
                "relative rounded-lg overflow-hidden aspect-[3/4] ring-1 transition-all",
                selected?.id === o.id ? "ring-white" : "ring-white/8 hover:ring-white/20"
              )}
            >
              <img src={o.url} alt={o.name} loading="lazy" className="h-full w-full object-cover" />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1.5">
                <span className="text-[9px] text-zinc-300">{o.name}</span>
              </div>
            </button>
          ))}
        </div>

        {browser.hasMore && (
          <button
            onClick={browser.loadMore}
            className="mt-3 w-full rounded-lg ring-1 ring-white/10 py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1.5"
          >
            <ChevronDown className="h-3 w-3" /> Load more
          </button>
        )}
        {browser.total === 0 && <EmptyState label="outfits" />}
      </div>

      <div className="mt-3 flex gap-2">
        <label className="flex-1 cursor-pointer rounded-lg ring-1 ring-white/10 py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1">
          <ImageIcon className="h-3 w-3" /> Upload
          <input type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onUpload?.(f); }} />
        </label>
        <button onClick={onOpenDesigner} className="flex-1 rounded-lg ring-1 ring-white/10 py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1">
          <Wand2 className="h-3 w-3" /> Designer
        </button>
      </div>
    </section>
  );
}