import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAssetBrowser } from "@/components/studio/useAssetBrowser";
import { SearchBox, CategoryChips, CountLine } from "@/components/studio/assetBrowserParts";
import PoseIcon from "@/components/studio/PoseIcon";

// A searchable, category-filtered browser for the big libraries.
//
// The first version of the composer put 551 poses and 250 arrangements into raw
// <select> elements. A dropdown is fine for nine aspect ratios and useless for
// five hundred poses: you cannot search it, the categories are invisible until
// you open it, and there is no way to read what an entry actually says before
// choosing it. This is the same mistake as the outfit dropdown that read
// "Casual1" — and the fix is the same, which is to use the browser that already
// exists for exactly this in the Shoot tab rather than writing a worse one.
//
// `icons` turns on the pose glyphs. Arrangements have no glyph vocabulary, so
// they render as text tiles instead of a grid of identical figures.
export default function BrowsePicker({ label, hint, groups, selected, onSelect,
                                       icons = false, emptyLabel = "not set" }) {
  const [open, setOpen] = useState(false);
  const categories = Object.keys(groups || {});
  const items = categories.flatMap((cat) => (groups[cat] || []).map((p) => ({ ...p, category: cat })));
  const browser = useAssetBrowser({ items, categories, pageSize: icons ? 24 : 18 });
  const chosen = items.find((p) => p.id === selected);

  return (
    <div className="rounded-lg ring-1 ring-white/8 bg-white/[0.02]">
      <button type="button" onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-2.5 py-2 text-left">
        <span className="flex-1 min-w-0">
          <span className="block text-[10px] text-zinc-500">
            {label}{hint && <span className="text-zinc-600"> · {hint}</span>}
          </span>
          <span className={cn("block text-[11px] truncate",
            chosen ? "text-zinc-200" : "text-zinc-600")}>
            {chosen ? chosen.label : emptyLabel}
          </span>
        </span>
        {chosen && (
          <span onClick={(e) => { e.stopPropagation(); onSelect(""); }}
            className="text-[10px] text-zinc-500 hover:text-zinc-200 px-1">clear</span>
        )}
        <ChevronDown className={cn("h-3.5 w-3.5 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="px-2.5 pb-2.5">
          <SearchBox value={browser.query} onChange={browser.setQuery}
                     placeholder={`Search ${label.toLowerCase()}…`} />
          <CategoryChips categories={categories} active={browser.category} onSelect={browser.setCategory} />
          <CountLine visible={browser.visible.length} total={browser.total} />

          {/* The chosen entry's full text, readable before committing to it.
              What an arrangement SAYS is the whole point — "cheek to cheek"
              turns both heads 30 degrees, and that is only visible in the text. */}
          {chosen && (
            <div className="mt-2 rounded-lg ring-1 ring-white/10 bg-white/[0.03] px-2.5 py-2">
              <div className="text-[10px] text-zinc-400 leading-snug">{chosen.text}</div>
            </div>
          )}

          <div className="mt-2 max-h-[300px] overflow-y-auto">
            {icons ? (
              <div className="grid gap-1.5 p-1 grid-cols-[repeat(auto-fill,minmax(58px,1fr))]">
                {browser.visible.map((p) => (
                  <button key={p.id} type="button" onClick={() => { onSelect(p.id); setOpen(false); }}
                    title={p.text}
                    className={cn("aspect-square rounded-lg ring-1 flex flex-col items-center justify-center gap-1 p-1",
                      selected === p.id
                        ? "ring-2 ring-emerald-400 bg-emerald-500/10 text-white"
                        : "ring-white/8 bg-white/[0.02] text-zinc-400 hover:ring-white/25 hover:text-zinc-200")}>
                    <PoseIcon id={p.id} category={p.category} className="h-6 w-6" />
                    <span className="w-full text-[8px] leading-tight text-center line-clamp-2">{p.label}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="grid gap-1 p-1 sm:grid-cols-2">
                {browser.visible.map((p) => (
                  <button key={p.id} type="button" onClick={() => { onSelect(p.id); setOpen(false); }}
                    title={p.text}
                    className={cn("rounded-lg ring-1 px-2 py-1.5 text-left",
                      selected === p.id
                        ? "ring-2 ring-emerald-400 bg-emerald-500/10"
                        : "ring-white/8 bg-white/[0.02] hover:ring-white/25")}>
                    <span className="block text-[10px] text-zinc-200 leading-tight">{p.label}</span>
                    <span className="block text-[9px] text-zinc-500 leading-snug line-clamp-2 mt-0.5">{p.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {browser.hasMore && (
            <button type="button" onClick={browser.loadMore}
              className="mt-1.5 w-full rounded-lg ring-1 ring-white/10 py-1 text-[10px] text-zinc-400 hover:text-zinc-200 hover:ring-white/25">
              show more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
