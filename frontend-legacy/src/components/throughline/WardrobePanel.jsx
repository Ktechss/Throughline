import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

// Right-side wardrobe manager: pick an outfit (→ @image2), see its full image and
// the description it was made with up top, filter by category, and delete outfits.
// items: [{ id, file, description, category }]; selected = the chosen outfit id.
export default function WardrobePanel({ items, selected, onSelect, onDelete, onUpload, stamp }) {
  const [cat, setCat] = useState('All')
  const sel = items.find((i) => i.id === selected)
  // categories present, in first-seen order, with counts
  const cats = []
  for (const it of items) { const c = it.category || 'Uncategorized'; if (!cats.includes(c)) cats.push(c) }
  const shown = cat === 'All' ? items : items.filter((i) => (i.category || 'Uncategorized') === cat)
  return (
    <section className="eve-panel self-start lg:sticky lg:top-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="eve-label">wardrobe <span className="text-[#4ea1ff]">→ @image2</span></h3>
        <span className="font-mono text-[10px] text-[#666674]">{items.length} saved</span>
      </div>

      {/* category filter */}
      {cats.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {['All', ...cats].map((c) => (
            <button key={c} onClick={() => setCat(c)}
              className={`rounded-full border px-2 py-0.5 text-[10px] transition ${cat === c
                ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
                : 'border-[#2a2a34] text-[#8a8a99] hover:border-[#3a3a46]'}`}>
              {c}{c !== 'All' && <span className="ml-1 text-[#5f6b7a]">{items.filter((i) => (i.category || 'Uncategorized') === c).length}</span>}
            </button>
          ))}
        </div>
      )}

      {/* selected outfit — category + description first, then the full image */}
      {sel ? (
        <div className="mb-4 rounded-lg border border-[#284d72] bg-[#0e1722] p-3">
          <p className="eve-label text-[#67aff8]">selected · {sel.id}{sel.category && <span className="ml-2 rounded-full bg-[#123049] px-1.5 py-0.5 text-[9px] text-[#9fd0ff]">{sel.category}</span>}</p>
          <p className="mt-1 text-[11px] leading-relaxed text-[#aab4c0]">
            {sel.description
              ? <><span className="text-[#5f6b7a]">made with: </span>{sel.description}</>
              : <span className="italic text-[#6c6c79]">uploaded outfit — no description saved</span>}
          </p>
          <img src={`/api/wardrobe/${sel.file}/file?t=${stamp}`}
            className="mt-2 w-full rounded-md border border-[#24242e]" alt={sel.id} />
        </div>
      ) : (
        <p className="mb-4 text-[11px] text-[#767684]">
          Select an outfit below to see its full image and the description it was made with.
        </p>
      )}

      {/* grid of outfits — click to select, hover to delete */}
      <div className="grid grid-cols-5 gap-2">
        <button onClick={() => onSelect('')}
          className={`flex aspect-[3/4] flex-col items-center justify-center gap-1 rounded-md border text-[10px] transition ${!selected
            ? 'border-[#4ea1ff] bg-[#123049] text-[#9fd0ff]'
            : 'border-[#2a2a34] text-[#8a8a99] hover:border-[#3a3a46]'}`}>
          <span className="text-lg">∅</span>none
        </button>
        {shown.map((item) => (
          <div key={item.id} onClick={() => onSelect(item.id)}
            className={`group relative cursor-pointer overflow-hidden rounded-md border transition ${selected === item.id
              ? 'border-[#4ea1ff] ring-1 ring-[#4ea1ff]'
              : 'border-[#2a2a34] hover:border-[#3a3a46]'}`}>
            <img src={`/api/wardrobe/${item.file}/thumb?t=${stamp}`} loading="lazy" decoding="async"
              className="aspect-[3/4] w-full object-cover" alt={item.id} />
            <span className="block truncate px-1 py-0.5 text-[9px] text-[#aaaab6]">{item.id}</span>
            <button onClick={(e) => { e.stopPropagation(); onDelete(item) }} title="delete outfit"
              className="absolute right-1 top-1 rounded bg-black/60 p-1 text-[#e2564a] opacity-0 transition hover:bg-black/85 group-hover:opacity-100">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
        <label className="flex aspect-[3/4] cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-[#3a3a46] text-[10px] text-[#8a8a99] transition hover:border-[#4ea1ff] hover:text-[#cfe0f5]">
          <Plus className="h-5 w-5" />+ outfit
          <input className="hidden" type="file" accept="image/*" onChange={onUpload} />
        </label>
      </div>
    </section>
  )
}
