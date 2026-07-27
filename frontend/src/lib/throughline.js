// API helper + view adapters that map Throughline's real backend shapes onto the
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
  { key: 'hair', label: 'Hair (style & colour)', hint: 'e.g. sleek high ponytail, jet black', clause: 'Hairstyle' },
  { key: 'jewellery', label: 'Jewellery', hint: 'earrings, necklace, bracelets', clause: 'Jewellery' },
  { key: 'bag', label: 'Bag / clutch', hint: 'e.g. black leather shoulder bag', clause: 'Bag' },
  { key: 'outerwear', label: 'Outerwear / layer', hint: 'jacket, coat, blazer, dupatta', clause: 'Outerwear' },
  { key: 'belt', label: 'Belt', hint: 'e.g. tan leather belt', clause: 'Belt' },
  { key: 'sunglasses', label: 'Sunglasses', hint: 'e.g. black cat-eye', clause: 'Eyewear' },
  { key: 'watch', label: 'Watch', hint: 'e.g. gold analog', clause: 'Watch' },
  { key: 'hair_accessory', label: 'Hair accessory', hint: 'scarf, headband, clip', clause: 'Hair accessory' },
  { key: 'hosiery', label: 'Hosiery', hint: 'opaque tights / stockings', clause: 'Hosiery (opaque)' },
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

// Wardrobe categories — grouping for the saved outfit library (a stylist's rack).
export const WARDROBE_CATEGORIES = [
  'Day Out', 'Night Out', 'Office', 'Party', 'Date', 'Ethnic',
  'Casual', 'Vacation', 'Festive', 'Costume', 'Other',
]

// Structured outfit pickers → sent to /api/wardrobe/enrich, where Claude expands
// them + a short idea into a rich, opaque, garment-only description. Single-select
// per group. Tasteful, fashion-forward, Western + Indian/ethnic (South-Delhi stylist).
export const OUTFIT_PICKERS = [
  { key: 'occasion', label: 'Occasion', options: [
    'everyday', 'work / office', 'brunch', 'date night', 'cocktail party',
    'wedding guest', 'festive / Diwali', 'sangeet', 'vacation', 'street style', 'athleisure'] },
  { key: 'style', label: 'Style / aesthetic', options: [
    'minimal', 'classic', 'boho', 'streetwear', 'old money', 'Y2K', 'edgy',
    'romantic', 'Indo-western', 'traditional ethnic', 'contemporary ethnic'] },
  { key: 'fabric', label: 'Fabric', options: [
    'cotton', 'linen', 'silk', 'satin', 'chiffon', 'georgette', 'velvet',
    'denim', 'wool', 'knit', 'leather', 'brocade', 'organza', 'crepe'] },
  { key: 'silhouette', label: 'Silhouette', options: [
    'fitted', 'tailored', 'A-line', 'bodycon', 'oversized', 'flowy',
    'wide-leg', 'peplum', 'mermaid', 'draped', 'structured'] },
  { key: 'formality', label: 'Formality', options: [
    'casual', 'smart casual', 'business', 'semi-formal', 'formal', 'black tie', 'festive'] },
  { key: 'season', label: 'Season', options: [
    'summer', 'monsoon', 'autumn', 'winter', 'spring', 'resort'] },
]

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
