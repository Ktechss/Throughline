import { ImageIcon, Wand2, ChevronDown, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAssetBrowser } from "./useAssetBrowser";
import { SearchBox, CategoryChips, CountLine, EmptyState } from "./assetBrowserParts";

export default function OutfitPicker({ outfits, selected, onSelect, onClear, onUpload, onOpenDesigner, onDelete }) {
  const categories = ["All", ...Array.from(new Set(outfits.map((o) => o.category)))];
  const browser = useAssetBrowser({ items: outfits, categories, pageSize: 12 });

  return (
    <div>
      <SearchBox value={browser.query} onChange={browser.setQuery} placeholder="Search outfits…" />
      <CategoryChips categories={categories} active={browser.category} onSelect={browser.setCategory} />
      <CountLine visible={browser.visible.length} total={browser.total} />

      {/* p-0.5 on the grid, not just pr-1 on the scroller. `ring-2` paints
          OUTSIDE the border box, and the grid sat flush against the scrollport
          on the top, bottom and left — so the emerald ring on any first-row or
          first-column tile was shaved flat and the selection read as a
          three-sided outline. The gutter gives the ring somewhere to land. */}
      <div className="mt-2 max-h-[360px] overflow-y-auto pr-1">
        <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(90px,1fr))] p-0.5">
          {browser.visible.map((o) => (
            <div
              key={o.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(o)}
              className={cn(
                "group relative rounded-lg overflow-hidden aspect-[3/4] ring-1 transition-all cursor-pointer",
                selected?.id === o.id ? "ring-2 ring-emerald-400" : "ring-line-subtle hover:ring-white/25"
              )}
            >
              <img src={o.url} alt={o.name} loading="lazy" className="h-full w-full object-cover" />
              {onDelete && (
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(o.id); }}
                  className="absolute top-1 right-1 z-10 rounded-md bg-black/60 p-1 text-zinc-300 opacity-0 group-hover:opacity-100 hover:text-rose-400 transition"
                  aria-label="Delete outfit"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1.5">
                <span className="text-[11px] text-zinc-300">{o.name}</span>
              </div>
            </div>
          ))}
        </div>

        {browser.hasMore && (
          <button
            onClick={browser.loadMore}
            className="mt-3 w-full rounded-lg ring-1 ring-line py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1.5"
          >
            <ChevronDown className="h-3 w-3" /> Load more
          </button>
        )}
        {browser.total === 0 && <EmptyState label="outfits" />}
      </div>

      <div className="mt-3 flex gap-2">
        <label className="flex-1 cursor-pointer rounded-lg ring-1 ring-line py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1">
          <ImageIcon className="h-3 w-3" /> Upload
          <input type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onUpload?.(f); }} />
        </label>
        <button onClick={onOpenDesigner} className="flex-1 rounded-lg ring-1 ring-line py-2 text-[11px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1">
          <Wand2 className="h-3 w-3" /> Designer
        </button>
      </div>
    </div>
  );
}