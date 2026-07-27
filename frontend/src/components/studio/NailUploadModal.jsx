import React, { useRef, useState } from "react";
import { X, Check } from "lucide-react";
import { cn } from "@/lib/utils";

// Common nail colours (the category). Swatch is just a UI hint.
const COLORS = [
  { name: "red", swatch: "#c0392b" }, { name: "pink", swatch: "#e8a0bf" },
  { name: "nude", swatch: "#d8b7a4" }, { name: "blue", swatch: "#3a5a9c" },
  { name: "green", swatch: "#3b7a57" }, { name: "purple", swatch: "#6b4a8a" },
  { name: "burgundy", swatch: "#5b1a2b" }, { name: "black", swatch: "#1c1c1e" },
  { name: "white", swatch: "#eef0f2" }, { name: "gold", swatch: "#c9a24b" },
  { name: "french", swatch: "#f3e9e2" }, { name: "glitter", swatch: "#b8b8c8" },
  { name: "chrome", swatch: "#b9c2cc" }, { name: "other", swatch: "#6b6b76" },
];

// On upload, pick a colour — that's it. Name auto = <colour><n>; the image is the
// reference (no description / no Claude). onSave({ file, color }).
export default function NailUploadModal({ file, existingColors = [], onSave, onClose }) {
  const [color, setColor] = useState("");
  const [saving, setSaving] = useState(false);
  const url = useRef(null);
  if (!url.current && file) url.current = URL.createObjectURL(file);

  const extras = existingColors.filter((c) => !COLORS.some((x) => x.name === c));

  const save = async () => {
    if (!color || saving) return;
    setSaving(true);
    await onSave({ file, color });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onMouseDown={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d0d0f] overflow-hidden" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h3 className="text-[14px] font-semibold">Add nail style</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="p-5 flex gap-4 items-start">
          <img src={url.current} alt="nail" className="h-36 w-28 shrink-0 rounded-lg object-cover ring-1 ring-white/10" />
          <div className="flex-1 min-w-0">
            <label className="text-[11px] text-zinc-400">Colour</label>
            <p className="text-[10px] text-zinc-600 mb-2">Saved as <span className="font-mono text-zinc-400">{color ? `${color}<n>` : "colour<n>"}</span> — the image is the reference.</p>
            <div className="flex flex-wrap gap-1.5">
              {[...COLORS.map((c) => c.name), ...extras].map((c) => {
                const sw = COLORS.find((x) => x.name === c)?.swatch || "#6b6b76";
                return (
                  <button key={c} type="button" onClick={() => setColor(c)}
                    className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ring-1 capitalize transition-colors",
                      color === c ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-300 hover:ring-white/25")}>
                    <span className="h-2.5 w-2.5 rounded-full ring-1 ring-black/20" style={{ background: sw }} />{c}
                  </button>
                );
              })}
            </div>
            <input value={color} onChange={(e) => setColor(e.target.value.trim().toLowerCase())} placeholder="or type a colour…"
              className="mt-3 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />
          </div>
        </div>

        <div className="border-t border-white/5 px-5 py-3 flex justify-end gap-2">
          <button onClick={onClose} disabled={saving} className="rounded-lg ring-1 ring-white/10 px-4 py-2 text-[13px] text-zinc-300 hover:bg-white/5 disabled:opacity-40">Cancel</button>
          <button onClick={save} disabled={!color || saving} className="rounded-lg bg-white text-black px-4 py-2 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-2">
            <Check className="h-4 w-4" /> Save
          </button>
        </div>
      </div>
    </div>
  );
}
