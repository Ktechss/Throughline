// API helper + view adapters that map eve1's real backend shapes onto the
// props the ported eve-pixel-pulse components expect.

export const api = {
  async get(u) { const r = await fetch(u); if (!r.ok) throw new Error(await r.text()); return r.json() },
  async send(u, method, body) {
    const r = await fetch(u, {
      method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.text()).slice(0, 300))
    return r.json()
  },
  async upload(u, file) {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch(u, { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.text()).slice(0, 300))
    return r.json()
  },
}

export const ep = (s) => (s || '').replace('fal-ai/', '').replace('openai/', '')

// Small details a reference photo often crops out — highlighted after a describe
// so the user can supply what the image didn't show. `clause` is how each is
// phrased into the final outfit description sent to the turnaround generator.
export const DETAIL_FIELDS = [
  { key: 'outfit_color', label: 'Outfit colour', hint: 'e.g. emerald green', clause: 'Outfit colour' },
  { key: 'lower_garment', label: 'Lower garment', hint: 'shorts / skirt / pants / jeans / dress', clause: 'Lower garment' },
  { key: 'shoes', label: 'Shoes / heels', hint: 'e.g. black strappy heels', clause: 'Footwear' },
  { key: 'fingernails', label: 'Fingernail colour', hint: 'both hands', clause: 'Fingernail polish' },
  { key: 'toenails', label: 'Toenail colour', hint: 'both feet', clause: 'Toenail polish' },
  { key: 'lipstick', label: 'Lipstick colour', hint: 'e.g. dusty rose', clause: 'Lipstick' },
]

// prose + filled detail fields -> the final outfit description.
export function mergeOutfit(prose, details) {
  const extra = DETAIL_FIELDS
    .map((f) => { const v = (details?.[f.key] || '').trim(); return v ? `${f.clause}: ${v}` : null })
    .filter(Boolean)
  return extra.length ? `${(prose || '').trim()} ${extra.join('. ')}.` : (prose || '').trim()
}

export const STAGE = {
  starting: 'Starting…',
  generating: 'Generating…',
  'moderation retry': 'Moderation flagged — retrying…',
  'scene-model fallback': 'Refused — trying scene model…',
  'scene-model moderation retry': 'Scene-model retry…',
  downloading: 'Downloading…',
  'leveling & gating': 'Checking identity…',
  done: 'Done', failed: 'Failed',
}

// A finished run -> the flat shape GenerationCard / VerdictChips / Review use.
export function runView(r) {
  const v = r.verdict || {}
  return {
    id: r.id,
    running: false,
    image: `/api/images/${r.file}`,
    thumb: `/api/images/${r.file}/thumb`,   // ~512px JPEG for grids — full image only in detail
    status: v.status || 'ungated',
    score: v.similarity ?? null,
    yaw: v.yaw ?? 0,
    px: v.face_px ?? null,
    poseMismatch: !!v.pose_mismatch,
    label: r.session?.label || 'shot',
    created: (r.created || '').replace('T', ' '),
    model: ep(r.endpoint) + (r.moderation_fallback ? ' · scene' : ''),
    mark: r.mark,
    raw: r,
  }
}

// A live generation card (may still be running).
export function genView(g) {
  const st = g.status || {}
  if (st.done && st.error) return { id: g.jid, error: String(st.error).slice(0, 160), label: g.label }
  if (st.done && g.run) return runView(g.run)
  return {
    id: g.jid, running: true,
    stage: STAGE[st.stage] || st.stage || 'starting…',
    retry: st.retry, elapsed: Math.round(st.elapsed || 0), label: g.label,
  }
}
