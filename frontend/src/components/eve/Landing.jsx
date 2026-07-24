import { useState } from 'react'
import { Plus, Trash2, ShieldCheck, CircleDashed, LoaderCircle } from 'lucide-react'

// Netflix-style profile picker: every character is a face you step into. Pick one
// to enter its studio (its own identity, calibration, wardrobe and generations),
// or create a new one — which starts blank and runs its own calibration.
function Avatar({ c }) {
  const [broken, setBroken] = useState(false)
  const initials = (c.name || c.id).slice(0, 2).toUpperCase()
  if (c.has_avatar && !broken) {
    return (
      <img src={`/api/characters/${c.id}/avatar`} alt={c.name} onError={() => setBroken(true)}
        className="h-full w-full object-cover" />
    )
  }
  return (
    <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[#1b2b3d] to-[#0f1620] font-mono text-3xl font-semibold text-[#5f7da0]">
      {initials}
    </div>
  )
}

export default function Landing({ characters, active, onSelect, onCreate, onDelete }) {
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const n = name.trim()
    if (!n || busy) return
    setBusy(true)
    try { await onCreate(n, desc.trim()) } finally { setBusy(false); setCreating(false); setName(''); setDesc('') }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0c0c0f] px-6 py-16 text-[#e6e6ea]">
      <div className="mb-1 flex items-center gap-2 font-mono text-sm font-semibold text-[#8a8a99]">
        <span className="h-2 w-2 rounded-full bg-[#4ea1ff]" /> eve1 · studios
      </div>
      <h1 className="mb-2 text-3xl font-semibold tracking-tight">Who are we shooting?</h1>
      <p className="mb-12 text-sm text-[#767684]">Pick a character to enter her studio, or create a new one.</p>

      <div className="flex flex-wrap items-start justify-center gap-7">
        {characters.map((c) => (
          <div key={c.id} className="group flex w-36 flex-col items-center">
            <button onClick={() => onSelect(c.id)}
              className={`relative aspect-square w-36 overflow-hidden rounded-2xl border-2 transition ${c.id === active
                ? 'border-[#4ea1ff]'
                : 'border-transparent hover:border-[#4a6a8f]'} group-hover:scale-[1.04]`}>
              <Avatar c={c} />
              {c.id !== active && characters.length > 1 && (
                <span onClick={(e) => { e.stopPropagation(); onDelete(c) }} title="delete character"
                  className="absolute right-1.5 top-1.5 z-10 rounded bg-black/60 p-1 text-[#e2564a] opacity-0 transition hover:bg-black/85 group-hover:opacity-100">
                  <Trash2 className="h-3.5 w-3.5" />
                </span>
              )}
            </button>
            <span className="mt-3 max-w-full truncate text-sm font-medium text-[#cdcdd6] group-hover:text-[#e6e6ea]">{c.name}</span>
            <span className={`mt-0.5 flex items-center gap-1 font-mono text-[10px] ${c.has_identity ? 'text-[#33c07f]' : 'text-[#d99a2b]'}`}>
              {c.has_identity ? <><ShieldCheck className="h-3 w-3" /> identity set</> : <><CircleDashed className="h-3 w-3" /> needs calibration</>}
            </span>
          </div>
        ))}

        {/* create card */}
        <div className="flex w-36 flex-col items-center">
          <button onClick={() => setCreating(true)}
            className="flex aspect-square w-36 items-center justify-center rounded-2xl border-2 border-dashed border-[#2f2f3a] text-[#5f5f6c] transition hover:border-[#4ea1ff] hover:text-[#9fd0ff]">
            <Plus className="h-9 w-9" />
          </button>
          <span className="mt-3 text-sm font-medium text-[#767684]">New character</span>
        </div>
      </div>

      {creating && (
        <div onClick={() => !busy && setCreating(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6">
          <div onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[#24242e] bg-[#0f0f14] p-6">
            <h2 className="text-lg font-semibold">Create a character</h2>
            <p className="mt-1 text-xs text-[#8a8a99]">Describe her and Claude writes her bio, then generates her first face. You'll calibrate it next to lock strong consistency.</p>
            <label className="mt-4 block eve-label text-[#8a8a99]">name</label>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              placeholder="e.g. Anya, Meera, Zoya…"
              className="mt-1 w-full rounded-lg border border-[#2a2a34] bg-[#08080b] px-3 py-2.5 text-sm outline-none focus:border-[#4ea1ff]" />
            <label className="mt-3 block eve-label text-[#8a8a99]">description <span className="text-[#5f5f6c]">— who is she?</span></label>
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={4}
              placeholder="e.g. 24, Punjabi, warm honey skin, sharp jawline and high cheekbones, long wavy dark-brown hair, athletic hourglass build, a small mole near her lip"
              className="mt-1 w-full resize-none rounded-lg border border-[#2a2a34] bg-[#08080b] px-3 py-2.5 text-sm leading-relaxed outline-none focus:border-[#4ea1ff]" />
            <p className="mt-1.5 text-[10px] text-[#5f5f6c]">Optional — leave blank and Claude invents a coherent person. Keep it visual; avoid explicit wording.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setCreating(false)} disabled={busy}
                className="rounded-lg border border-[#2a2a34] px-4 py-2 text-sm text-[#a9a9b6] transition hover:border-[#3a3a46]">Cancel</button>
              <button onClick={submit} disabled={busy || !name.trim()}
                className="flex items-center gap-2 rounded-lg bg-[#4ea1ff] px-4 py-2 text-sm font-medium text-[#07111b] transition hover:bg-[#70b3ff] disabled:opacity-40">
                {busy && <LoaderCircle className="h-4 w-4 animate-spin" />} Create character
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
