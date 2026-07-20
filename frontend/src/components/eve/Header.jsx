import { Circle } from 'lucide-react'

export default function Header({ tab, setTab, count, gallery }) {
  const angles = gallery?.entries?.length || 0
  return (
    <header className="sticky top-0 z-40 border-b border-[#24242e] bg-[#0c0c0f]/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1180px] items-center px-5">
        <div className="mr-10 flex items-center gap-2 font-mono text-lg font-semibold">
          <Circle className="h-2.5 w-2.5 fill-[#4ea1ff] text-[#4ea1ff]" />eve1
        </div>
        <nav className="flex h-full gap-7">
          {['shoot', 'bio', 'calibrate', 'video', 'review'].map((item) => (
            <button key={item} onClick={() => setTab(item)}
              className={`relative text-xs font-semibold uppercase tracking-[.18em] transition ${tab === item ? 'text-[#e6e6ea]' : 'text-[#70707d] hover:text-[#b8b8c3]'}`}>
              {item}
              {item === 'review' && <span className="ml-2 rounded-full bg-[#24242e] px-1.5 py-0.5 font-mono text-[9px]">{count}</span>}
              {tab === item && <span className="absolute inset-x-0 -bottom-[19px] h-px bg-[#4ea1ff]" />}
            </button>
          ))}
        </nav>
        <div className="ml-auto hidden items-center gap-2 font-mono text-[11px] text-[#8a8a99] sm:flex">
          <span className={`h-1.5 w-1.5 rounded-full ${angles ? 'bg-[#33c07f]' : 'bg-[#d99a2b]'}`} />
          gallery: {angles ? `${angles} angles ready` : 'empty — ungated'}
        </div>
      </div>
    </header>
  )
}
