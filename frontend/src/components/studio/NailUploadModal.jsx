import React, { useEffect, useRef, useState } from "react";
import { X, Loader2, Check } from "lucide-react";
import { cn } from "@/lib/utils";

// Modal shown when a nail image is picked: name it, categorise it, review the
// auto-description, then save. onDescribe(file) -> description; onSave({file,name,category,description}).
export default function NailUploadModal({ file, categories = [], onDescribe, onSave, onClose }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [describing, setDescribing] = useState(true);
  const [saving, setSaving] = useState(false);
  const url = useRef(null);
  if (!url.current && file) url.current = URL.createObjectURL(file);

  useEffect(() => {
    let alive = true;
    (async () => {
      try { const d = await onDescribe(file); if (alive) setDescription(d || ""); }
      catch { if (alive) setDescription(""); }
      finally { if (alive) setDescribing(false); }
    })();
    return () => { alive = false; if (url.current) URL.revokeObjectURL(url.current); };
  }, [file, onDescribe]);

  const save = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    await onSave({ file, name: name.trim(), category: category.trim(), description });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onMouseDown={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0d0d0f] overflow-hidden" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h3 className="text-[14px] font-semibold">Add nail style</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="p-5 flex gap-5">
          <img src={url.current} alt="nail" className="h-40 w-32 shrink-0 rounded-lg object-cover ring-1 ring-white/10" />
          <div className="flex-1 min-w-0 space-y-3">
            <div>
              <label className="text-[11px] text-zinc-400">Name <span className="text-rose-400">*</span></label>
              <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cherry-red almond"
                className="mt-1 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />
            </div>
            <div>
              <label className="text-[11px] text-zinc-400">Category</label>
              <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Everyday, Party, Ethnic" list="nail-cats"
                className="mt-1 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none" />
              <datalist id="nail-cats">{categories.map((c) => <option key={c} value={c} />)}</datalist>
              {categories.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {categories.map((c) => (
                    <button key={c} type="button" onClick={() => setCategory(c)}
                      className={cn("rounded-full px-2 py-0.5 text-[10px] ring-1 transition-colors", category === c ? "bg-white text-black ring-white" : "ring-white/10 text-zinc-400 hover:text-white")}>{c}</button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="px-5 pb-4">
          <label className="text-[11px] text-zinc-400 flex items-center gap-1.5">
            Description {describing && <span className="inline-flex items-center gap-1 text-zinc-500"><Loader2 className="h-3 w-3 animate-spin" /> reading nails…</span>}
          </label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            placeholder="nail shape, length, colour, finish, art…"
            className="mt-1 w-full rounded-lg bg-white/[0.03] ring-1 ring-white/10 px-3 py-2 text-[12px] text-zinc-200 focus:ring-white/30 outline-none resize-none" />
        </div>

        <div className="border-t border-white/5 px-5 py-3 flex justify-end gap-2">
          <button onClick={onClose} disabled={saving} className="rounded-lg ring-1 ring-white/10 px-4 py-2 text-[13px] text-zinc-300 hover:bg-white/5 disabled:opacity-40">Cancel</button>
          <button onClick={save} disabled={!name.trim() || saving} className="rounded-lg bg-white text-black px-4 py-2 text-[13px] font-medium hover:bg-zinc-200 disabled:opacity-40 flex items-center gap-2">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save nail style
          </button>
        </div>
      </div>
    </div>
  );
}
