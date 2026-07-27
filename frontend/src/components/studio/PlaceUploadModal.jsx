import React, { useRef, useState } from "react";
import { X, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const CATS = ["Home", "Bedroom", "Living room", "Kitchen", "Bathroom", "Office",
  "Cafe", "Restaurant", "Outdoor", "Street", "Garden", "Balcony", "Studio", "Other"];

// On upload, name the place and categorise it. Image-only (the photo is the
// reference). onSave({ file, name, category }).
export default function PlaceUploadModal({ file, existingCats = [], onSave, onClose }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [saving, setSaving] = useState(false);
  const url = useRef(null);
  if (!url.current && file) url.current = URL.createObjectURL(file);

  const cats = [...new Set([...CATS, ...existingCats])];

  const save = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    await onSave({ file, name: name.trim(), category: category.trim() });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onMouseDown={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0d0d0f] overflow-hidden" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h3 className="text-[14px] font-semibold">Add place</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="p-5 flex gap-4">
          <img src={url.current} alt="place" className="h-28 w-40 shrink-0 rounded-lg object-cover ring-1 ring-white/10" />
          <div className="flex-1 min-w-0 space-y-3">
            <div>
              <label className="text-[11px] text-zinc-400">Name <span className="text-rose-400">*</span></label>
              <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Her apartment — living room"
                className="mt-1 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />
            </div>
            <div>
              <label className="text-[11px] text-zinc-400">Category</label>
              <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Home" list="place-cats"
                className="mt-1 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />
              <datalist id="place-cats">{cats.map((c) => <option key={c} value={c} />)}</datalist>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {cats.slice(0, 10).map((c) => (
                  <button key={c} type="button" onClick={() => setCategory(c)}
                    className={cn("rounded-full px-2 py-0.5 text-[10px] ring-1 transition-colors", category === c ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{c}</button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-white/5 px-5 py-3 flex justify-end gap-2">
          <button onClick={onClose} disabled={saving} className="rounded-lg ring-1 ring-white/10 px-4 py-2 text-[13px] text-zinc-300 hover:bg-white/5 disabled:opacity-40">Cancel</button>
          <button onClick={save} disabled={!name.trim() || saving} className="rounded-lg bg-white text-black px-4 py-2 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-2">
            <Check className="h-4 w-4" /> Save place
          </button>
        </div>
      </div>
    </div>
  );
}
