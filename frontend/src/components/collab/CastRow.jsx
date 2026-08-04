import React, { useEffect, useState } from "react";
import { outfitView } from "@/api/throughline";
import { ChevronDown, Shirt, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import Picker, { ChipMulti } from "./Picker";
import BrowsePicker from "./BrowsePicker";

// Everything one member of the cast is wearing, doing and made up as.
//
// Her closet and her manicures are fetched with an explicit ?character= AND the
// X-Character header. Both, deliberately: the header scopes the JSON and the
// query parameter scopes the <img> thumbnails, which cannot send a header. That
// split is exactly how the wardrobe version of this bug reached the UI — the
// list was correctly scoped and every thumbnail still showed the active
// character's things.
export default function CastRow({ character, lib, value, onChange, framingOrder }) {
  const [outfits, setOutfits] = useState([]);
  const [nails, setNails] = useState([]);
  const [open, setOpen] = useState(false);
  const cid = character.id;

  useEffect(() => {
    let alive = true;
    const h = { "X-Character": cid };
    fetch(`/api/wardrobe?character=${cid}`, { headers: h })
      .then((r) => r.json())
      .then((d) => alive && setOutfits((d.wardrobe || []).map((o) => outfitView(o, cid))))
      .catch(() => {});
    fetch(`/api/nails?character=${cid}`, { headers: h })
      .then((r) => r.json())
      .then((d) => alive && setNails(d.nails || []))
      .catch(() => {});
    return () => { alive = false; };
  }, [cid]);

  const set = (k, v) => onChange({ ...value, [k]: v });
  const chosen = outfits.find((o) => o.id === value.outfit);
  const nail = nails.find((n) => n.id === value.nail);
  // Shoes only exist below a knee-up frame. The server drops them above it and
  // says so in the ledger; greying them out here is the same fact, earlier.
  const shoesVisible = framingOrder >= 5;

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
            {[chosen?.name, value.hair, value.makeup, nail?.name,
              (value.accessories || []).length ? `${value.accessories.length} accessories` : null]
              .filter(Boolean).join(" · ") || "nothing set — the scene decides"}
          </span>
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-3">
          <div>
            <span className="text-[10px] text-zinc-500">Outfit</span>
            {outfits.length === 0 ? (
              <p className="text-[11px] text-zinc-600 mt-1">no outfits saved for {character.name}</p>
            ) : (
              <div className="mt-1 grid grid-cols-[repeat(auto-fill,minmax(56px,1fr))] gap-1.5 max-h-40 overflow-y-auto">
                {outfits.map((o) => (
                  <button key={o.id} title={o.description || o.name}
                    onClick={() => set("outfit", value.outfit === o.id ? null : o.id)}
                    className={cn("relative aspect-[3/4] rounded-lg overflow-hidden ring-1",
                      value.outfit === o.id ? "ring-2 ring-emerald-400" : "ring-white/10 hover:ring-white/30")}>
                    <img src={o.url} alt={o.name} loading="lazy" className="h-full w-full object-cover" />
                    {value.outfit === o.id && (
                      <span className="absolute top-1 right-1 rounded-full bg-emerald-400 p-0.5">
                        <Check className="h-2 w-2 text-black" />
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {nails.length > 0 && (
            <div>
              <span className="text-[10px] text-zinc-500">
                Manicure <span className="text-zinc-600">· costs a reference slot</span>
              </span>
              <div className="mt-1 flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                {nails.map((n) => (
                  <button key={n.id} title={n.name}
                    onClick={() => set("nail", value.nail === n.id ? null : n.id)}
                    className={cn("h-10 w-10 rounded-lg overflow-hidden ring-1",
                      value.nail === n.id ? "ring-2 ring-emerald-400" : "ring-white/10 hover:ring-white/30")}>
                    <img src={`/api/nails/${n.file}/thumb?character=${cid}`} alt={n.name}
                         loading="lazy" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            {/* Hair STYLING only. Her colour, length and texture are identity and
                come from her reference — describing them here is the regression
                a9cc83cd exists to prevent. */}
            <Picker label="Hair" hint="styling only" groups={lib?.hair}
              value={value.hair} onChange={(v) => set("hair", v)}
              empty="as her reference" />
            <Picker label="Makeup" groups={lib?.makeup}
              value={value.makeup} onChange={(v) => set("makeup", v)}
              empty="her usual" />
            <Picker label="Footwear" groups={lib?.footwear} disabled={!shoesVisible}
              hint={shoesVisible ? null : "out of frame"}
              value={value.footwear} onChange={(v) => set("footwear", v)}
              empty="unspecified" className="col-span-2" />
          </div>

          {/* Her OWN pose — 551 of them, searchable. Distinct from the group
              arrangement: that says where everyone is relative to each other,
              this says what her body is doing inside it. */}
          <BrowsePicker label="Pose" hint={`${character.name} only`} icons
            groups={lib?.poses} selected={value.pose}
            onSelect={(v) => set("pose", v)} emptyLabel="however the scene reads" />

          <ChipMulti label="Accessories" hint="◐ sits on the face" groups={lib?.accessories}
            values={value.accessories || []} onChange={(v) => set("accessories", v)} />
        </div>
      )}
    </div>
  );
}
