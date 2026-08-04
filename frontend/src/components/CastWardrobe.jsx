import React, { useEffect, useState } from "react";
import { outfitView } from "@/api/throughline";
import { Shirt, ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

// One cast member's closet, shown as GARMENTS.
//
// The composer's first version used a <select> reading "Casual1 · Casual", which
// tells you nothing about the dress you are choosing — the thumbnails were
// already there (/api/wardrobe/{file}/thumb) and already used by the Shoot tab's
// OutfitPicker. This is that idea, sized for a row per character.
export default function CastWardrobe({ character, selected, onSelect, mode, onMode }) {
  const [outfits, setOutfits] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/api/wardrobe", { headers: { "X-Character": character.id } })
      .then((r) => r.json())
      .then((d) => { if (alive) setOutfits((d.wardrobe || []).map(outfitView)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [character.id]);

  const chosen = outfits.find((o) => o.id === selected);

  return (
    <div className="rounded-xl ring-1 ring-white/8 bg-white/[0.02]">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-3 px-3 py-2.5 text-left">
        {chosen ? (
          <img src={chosen.url} alt="" className="h-10 w-8 rounded object-cover ring-1 ring-white/15" />
        ) : (
          <span className="h-10 w-8 rounded ring-1 ring-white/10 flex items-center justify-center">
            <Shirt className="h-3.5 w-3.5 text-zinc-600" />
          </span>
        )}
        <span className="flex-1 min-w-0">
          <span className="block text-[12px] text-zinc-200">{character.name}</span>
          <span className="block text-[10px] text-zinc-500 truncate">
            {chosen ? `${chosen.name}${chosen.category ? ` · ${chosen.category}` : ""}` : "no outfit — describe it in the scene"}
          </span>
        </span>
        {/* An outfit can ride as an image or as its saved description. Both are
            real options: the description is rich, and the image costs a
            reference slot that identity is measured to care about. */}
        {chosen && (
          <span onClick={(e) => { e.stopPropagation(); onMode(mode === "text" ? "image" : "text"); }}
            className={cn("rounded-full px-2 py-0.5 text-[10px] ring-1 cursor-pointer",
              mode === "text" ? "ring-white/15 text-zinc-400" : "ring-emerald-400/40 text-emerald-300")}>
            {mode === "text" ? "as text" : "as image"}
          </span>
        )}
        <ChevronDown className={cn("h-3.5 w-3.5 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="px-3 pb-3">
          {outfits.length === 0 ? (
            <p className="text-[11px] text-zinc-500">no outfits saved for {character.name} yet</p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-1.5 max-h-56 overflow-y-auto">
              {outfits.map((o) => (
                <button key={o.id} title={o.description || o.name}
                  onClick={() => { onSelect(selected === o.id ? null : o.id); setOpen(false); }}
                  className={cn("relative aspect-[3/4] rounded-lg overflow-hidden ring-1 transition-all",
                    selected === o.id ? "ring-2 ring-emerald-400" : "ring-white/10 hover:ring-white/30")}>
                  <img src={o.url} alt={o.name} loading="lazy" className="h-full w-full object-cover" />
                  {selected === o.id && (
                    <span className="absolute top-1 right-1 rounded-full bg-emerald-400 p-0.5">
                      <Check className="h-2.5 w-2.5 text-black" />
                    </span>
                  )}
                  <span className="absolute inset-x-0 bottom-0 bg-black/70 text-[8px] text-zinc-300 px-1 py-0.5 truncate">
                    {o.name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
