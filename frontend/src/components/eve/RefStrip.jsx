import { Plus } from 'lucide-react'

// items: [{id, file}]; urlBase e.g. '/api/wardrobe' -> `${urlBase}/${file}/file`
export default function RefStrip({ title, tag, items, selected, onSelect, onUpload, urlBase }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="eve-label">{title} <span className="text-[#4ea1ff]">→ {tag}</span></h3>
        <span className="font-mono text-[10px] text-[#666674]">optional reference</span>
      </div>
      <div className="flex flex-wrap gap-2 pb-1">
        <button onClick={() => onSelect('')} className={`ref-card ${!selected ? 'ref-active' : ''}`}>
          <span className="text-lg text-[#676775]">∅</span><small>brief / default</small>
        </button>
        {items.map((item) => (
          <button key={item.id} onClick={() => onSelect(item.id)}
            className={`ref-card overflow-hidden ${selected === item.id ? 'ref-active' : ''}`}>
            <img src={`${urlBase}/${item.file}/file`} alt="" /><small>{item.id}</small>
          </button>
        ))}
        <label className="ref-card cursor-pointer border-dashed">
          <Plus className="h-5 w-5" /><small>+ {title.split(' ')[0]}</small>
          <input className="hidden" type="file" accept="image/*" onChange={onUpload} />
        </label>
      </div>
    </section>
  )
}
