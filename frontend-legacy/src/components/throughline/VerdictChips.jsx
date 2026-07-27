// v = a runView() (status/score/yaw/px/poseMismatch)
export default function VerdictChips({ v }) {
  const status = v?.status || 'ungated'
  const color = status === 'kept' ? 'bg-[#173a2c] text-[#62d99d]'
    : status === 'rejected' ? 'bg-[#40201f] text-[#f17b72]'
      : 'bg-[#3d3017] text-[#edb755]'
  return (
    <div className="flex flex-wrap gap-1.5 font-mono text-[9px] uppercase tracking-wide">
      <span className={`rounded px-1.5 py-1 ${color}`}>{status}</span>
      {v?.score != null && (
        <span className={`eve-chip font-bold ${v.poseMismatch ? 'line-through opacity-60' : ''}`}>sim {v.score.toFixed(2)}</span>
      )}
      <span className="eve-chip">yaw {v?.yaw > 0 ? '+' : ''}{v?.yaw || 0}°</span>
      {v?.px != null && <span className="eve-chip">{v.px}px</span>}
    </div>
  )
}
