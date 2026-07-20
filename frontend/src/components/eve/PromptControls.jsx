import { Sparkles, Wand2 } from 'lucide-react'

export default function PromptControls({
  brief, setBrief, prompt, setPrompt, onGenerate, onAiPrompt, aiBusy, selected, canGenerate,
}) {
  return (
    <>
      <label className="eve-label">shot brief</label>
      <textarea value={brief} onChange={(e) => setBrief(e.target.value)}
        className="eve-input mt-2 min-h-24 resize-none" placeholder="what’s the shot? place, moment, mood" />
      <div className="flex flex-wrap items-center gap-2 border-t border-[#24242e] pt-5">
        <button onClick={onGenerate} disabled={!canGenerate}
          className="eve-button bg-[#4ea1ff] text-[#07111b] hover:bg-[#70b3ff]"><Wand2 /> generate</button>
        <button onClick={onAiPrompt} disabled={aiBusy || !brief.trim()}
          className="eve-button border border-[#353541] hover:border-[#4ea1ff]">
          <Sparkles /> {aiBusy ? 'writing…' : 'AI prompt'}</button>
        <span className="ml-auto font-mono text-[10px] text-[#767684]">outfit {selected.outfit || '—'} · pose ref {selected.pose || '—'}</span>
      </div>
      {prompt && (
        <div className="rounded-lg border border-[#315d88] bg-[#101b27] p-3">
          <div className="mb-2 flex justify-between">
            <span className="eve-label text-[#72b8ff]">AI prompt (Claude)</span>
            <button onClick={() => setPrompt('')} className="text-[10px] text-[#7e9bb8]">clear · use template</button>
          </div>
          <textarea className="w-full resize-none bg-transparent font-mono text-[11px] leading-relaxed outline-none text-[#c7c7d0]"
            rows="4" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </div>
      )}
    </>
  )
}
