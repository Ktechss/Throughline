import { Circle, ChevronsUpDown } from 'lucide-react'

export default function Header({ tab, setTab, count, gallery, character, onSwitchCharacter }) {
  const angles = gallery?.entries?.length || 0
  return (
    <header className="sticky top-0 z-40 border-b border-[#24242e] bg-[#0c0c0f]/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1180px] items-center px-5">
        <div className="mr-10 flex items-center gap-2 font-mono text-lg font-semibold">
          <Circle className="h-2.5 w-2.5 fill-[#4ea1ff] text-[#4ea1ff]" />Throughline
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
        <div className="ml-auto flex items-center gap-4">
          <div className="hidden items-center gap-2 font-mono text-[11px] text-[#8a8a99] sm:flex">
            <span className={`h-1.5 w-1.5 rounded-full ${angles ? 'bg-[#33c07f]' : 'bg-[#d99a2b]'}`} />
            gallery: {angles ? `${angles} angles ready` : 'empty — ungated'}
          </div>
          {character && (
            <button onClick={onSwitchCharacter} title="switch character"
              className="flex items-center gap-2 rounded-full border border-[#24242e] bg-[#111117] py-1 pl-1 pr-2.5 transition hover:border-[#3a4a5e]">
              <span className="h-6 w-6 overflow-hidden rounded-full bg-[#1b2b3d]">
                <img src={`/api/characters/${character.id}/avatar`} alt={character.name}
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                  className="h-full w-full object-cover" />
              </span>
              <span className="max-w-[90px] truncate text-xs font-medium text-[#cdcdd6]">{character.name}</span>
              <ChevronsUpDown className="h-3.5 w-3.5 text-[#6b6b78]" />
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
