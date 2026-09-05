import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAssetBrowser } from "./useAssetBrowser";
import { SearchBox, CategoryChips, CountLine, EmptyState } from "./assetBrowserParts";
import PoseIcon from "./PoseIcon";

export default function PosePicker({ poses, selected, onSelect, onClear }) {
  // poses is an object keyed by category -> flatten into a single browsable list.
  const categories = Object.keys(poses);
  const items = categories.flatMap((cat) => poses[cat].map((p) => ({ ...p, category: cat })));
  const browser = useAssetBrowser({ items, categories, pageSize: 25 });

  return (
    <div>
      <SearchBox value={browser.query} onChange={browser.setQuery} placeholder="Search poses…" />
      <CategoryChips categories={categories} active={browser.category} onSelect={browser.setCategory} />
      <CountLine visible={browser.visible.length} total={browser.total} />

      {selected && (
        <div className="mt-2 rounded-lg ring-1 ring-line bg-surface px-2.5 py-2">
          <div className="text-[11px] font-medium text-zinc-200">{selected.label}</div>
          <div className="text-[10px] text-zinc-500 leading-snug line-clamp-2">{selected.text}</div>
        </div>
      )}

      <div className="mt-2 max-h-[360px] overflow-y-auto">
        <div className="grid gap-1.5 p-1 grid-cols-[repeat(auto-fill,minmax(62px,1fr))]">
          {browser.visible.map((p) => (
            <button
              key={p.id}
              onClick={() => onSelect(p)}
              title={p.text}
              className={cn(
                "aspect-square rounded-lg ring-1 flex flex-col items-center justify-center gap-1 p-1 transition-all",
                selected?.id === p.id
                  ? "ring-2 ring-emerald-400 bg-emerald-500/10 text-white"
                  : "ring-line-subtle bg-surface text-zinc-400 hover:ring-white/25 hover:text-zinc-200"
              )}
            >
              <PoseIcon id={p.id} category={p.category} className="h-6 w-6" />
              <span className="w-full text-[11px] leading-tight text-center line-clamp-2">{p.label}</span>
            </button>
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
        {browser.total === 0 && <EmptyState label="poses" />}
      </div>
    </div>
  );
}
