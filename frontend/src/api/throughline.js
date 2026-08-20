// Throughline API layer — talks to the FastAPI backend under /api (proxied to
// :8000 in dev). Ported from the legacy frontend's lib.

// Which character this tab is looking at. Sent on every request as X-Character
// so the SERVER never has to guess from a global that another tab, another
// window or a script may have moved underneath it — that is how an outfit
// generated for one character ended up filed under a different one.
let _character = null
export const setApiCharacter = (id) => { _character = id || null }
export const apiCharacter = () => _character

// URL for a per-character REFERENCE image, scoped.
//
// An <img> cannot send X-Character, and reference filenames collide across
// characters by design — every one of them has a calib-front.png and a
// body-canonical.webp. So an unscoped /api/refs/... does not 404, it silently
// serves whoever is active: that is how one character's calibration face turned
// up inside another's Bio tab. Same fix, same reason, as outfitView().
export const refUrl = (name, kind = "file") => {
  if (!name) return ""
  const q = _character ? `?character=${encodeURIComponent(_character)}` : ""
  return `/api/refs/${name}/${kind}${q}`
}
const _headers = (base = {}) => (_character ? { ...base, "X-Character": _character } : base)

export const api = {
  async get(u) {
    const r = await fetch(u, { headers: _headers() })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async send(u, method, body) {
    const r = await fetch(u, {
      method,
      headers: _headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.text()).slice(0, 300))
    return r.json()
  },
  async upload(u, file) {
    const fd = new FormData()
    fd.append("file", file)
    const r = await fetch(u, { method: "POST", body: fd, headers: _headers() })
    if (!r.ok) throw new Error((await r.text()).slice(0, 300))
    return r.json()
  },
}

// Strip the provider prefix from an endpoint id for display.
export const ep = (s) => (s || "").replace("fal-ai/", "").replace("openai/", "")

export const STAGE = {
  starting: "Starting…",
  generating: "Generating…",
  "moderation retry": "Moderation flagged — retrying…",
  "scene-model fallback": "Refused — trying scene model…",
  "scene-model moderation retry": "Scene-model retry…",
  downloading: "Downloading…",
  "leveling & gating": "Checking identity…",
  done: "Done",
  failed: "Failed",
}

// A finished run -> the flat shape the new UI cards/verdict chip use.
export function runView(r) {
  const v = r.verdict || {}
  // `kind` is what every consumer branches on. A clip is served from the same
  // /api/images path (FileResponse types it by extension and honours Range, so
  // <video> can seek), and its thumb is a poster frame the backend decodes —
  // the grid asks for both exactly as it does for a still.
  const video = (r.kind || "") === "video"
  return {
    id: r.id,
    running: false,
    kind: video ? "video" : "image",
    duration: video ? (r.duration ?? null) : null,
    url: `/api/images/${r.file}`,
    thumb: `/api/images/${r.file}/thumb`,
    status: v.status || "ungated",
    pov: !!r.meta?.pov,
    similarity: v.similarity ?? null,
    yaw: v.yaw ?? null,
    facePx: v.face_px ?? null,
    poseMismatch: !!v.pose_mismatch,
    brief: r.session?.label || r.meta?.brief || "shot",
    created: (r.created || "").replace("T", " "),
    model: ep(r.endpoint) + (r.moderation_fallback ? " · scene" : ""),
    mark: r.mark,
    raw: r,
  }
}

// A live generation card (may still be running) -> the ShootTab card shape.
export function genView(g) {
  const st = g.status || {}
  if (st.done && st.error)
    return { id: g.jid, stage: "error", error: String(st.error).slice(0, 160), brief: g.label }
  if (st.done && g.run) return { ...runView(g.run), stage: "done" }
  return {
    id: g.jid,
    stage: "running",
    stageLabel: STAGE[st.stage] || st.stage || "starting…",
    retry: st.retry,
    elapsed: Math.round(st.elapsed || 0),
    brief: g.label,
  }
}

// Regroup the flat /api/pose-library list into { category: [{id,label,text}] }
// for the PosePicker, and keep insertion order via the categories array.
export function groupPoses(poses, categories) {
  const out = {}
  for (const c of categories || []) out[c] = []
  for (const p of poses || []) {
    const cat = p.category || "Other"
    ;(out[cat] ||= []).push({ id: p.id, label: prettyPoseId(p.id), text: p.text })
  }
  // drop empty categories
  for (const k of Object.keys(out)) if (!out[k].length) delete out[k]
  return out
}

const prettyPoseId = (id) =>
  (id || "").replace(/[-_]/g, " ").replace(/\b\w/g, (m) => m.toUpperCase())

// Wardrobe row -> OutfitPicker item. Immutable filenames, so NO cache-buster
// on the thumbnail (that was the wasteful re-download the legacy UI had).
//
// `cid` names whose wardrobe when it is NOT the active character — the scene
// composer shows several closets at once. An <img> cannot send the X-Character
// header, so the character has to travel in the URL; without it every thumbnail
// falls back to the active character and you see one woman's dress in another's
// picker. Omitted for the Shoot tab, where the active character IS the subject.
export function outfitView(w, cid) {
  const q = cid ? `?character=${encodeURIComponent(cid)}` : ""
  return { id: w.id, name: w.id, category: w.category || "Uncategorized", file: w.file,
           description: w.description || "", url: `/api/wardrobe/${w.file}/thumb${q}` }
}

// Nail-style row -> picker item. Immutable filename, so no cache-buster.
export function nailView(n) {
  return {
    id: n.id, file: n.file, url: `/api/nails/${n.file}/thumb`,
    name: n.name || n.id, category: n.category || "Uncategorized",
    description: n.description || "",
  }
}

// Character row -> Landing card shape.
export function charView(c) {
  return {
    id: c.id,
    name: c.name,
    avatar: c.has_avatar ? `/api/characters/${c.id}/avatar` : null,
    initials: (c.name || c.id).slice(0, 2).toUpperCase(),
    identityStatus: c.has_identity ? "identity_set" : "needs_calibration",
    // Distinct from identityStatus, and stricter: a character with no master
    // face cannot be photographed at all, so the roster gates entry on this
    // rather than merely badging it.
    has_reference: !!c.has_reference,
    pending_faces: c.pending_faces || 0,
    // ready | awaiting_face | building | stalled — derived server-side so the
    // roster never has to infer a draft's state from a job id it may not have.
    status: c.status || "ready",
    job: c.job || null,
    bio: c.bio || "",
  }
}

// ---- Outfit designer -------------------------------------------------------
// Small details a reference photo often crops out — highlighted after a describe.
export const DETAIL_FIELDS = [
  { key: "outfit_color", label: "Outfit colour", hint: "e.g. emerald green", clause: "Outfit colour" },
  { key: "lower_garment", label: "Lower garment", hint: "shorts / skirt / pants / jeans / dress", clause: "Lower garment" },
  { key: "shoes", label: "Shoes / heels", hint: "e.g. black strappy heels", clause: "Footwear" },
  { key: "hair", label: "Hair (style & colour)", hint: "e.g. sleek high ponytail, jet black", clause: "Hairstyle" },
  { key: "jewellery", label: "Jewellery", hint: "earrings, necklace, bracelets", clause: "Jewellery" },
  { key: "bag", label: "Bag / clutch", hint: "e.g. black leather shoulder bag", clause: "Bag" },
  { key: "outerwear", label: "Outerwear / layer", hint: "jacket, coat, blazer, dupatta", clause: "Outerwear" },
  { key: "belt", label: "Belt", hint: "e.g. tan leather belt", clause: "Belt" },
  { key: "sunglasses", label: "Sunglasses", hint: "e.g. black cat-eye", clause: "Eyewear" },
  { key: "watch", label: "Watch", hint: "e.g. gold analog", clause: "Watch" },
  { key: "hair_accessory", label: "Hair accessory", hint: "scarf, headband, clip", clause: "Hair accessory" },
  { key: "hosiery", label: "Hosiery", hint: "opaque tights / stockings", clause: "Hosiery (opaque)" },
  { key: "fingernails", label: "Fingernail colour", hint: "both hands", clause: "Fingernail polish" },
  { key: "toenails", label: "Toenail colour", hint: "both feet", clause: "Toenail polish" },
  { key: "lipstick", label: "Lipstick colour", hint: "e.g. dusty rose", clause: "Lipstick" },
]

// prose + filled detail fields -> the final outfit description.
export function mergeOutfit(prose, details) {
  const extra = DETAIL_FIELDS
    .map((f) => { const v = (details?.[f.key] || "").trim(); return v ? `${f.clause}: ${v}` : null })
    .filter(Boolean)
  return extra.length ? `${(prose || "").trim()} ${extra.join(". ")}.` : (prose || "").trim()
}

export const WARDROBE_CATEGORIES = [
  "Day Out", "Night Out", "Office", "Party", "Date", "Ethnic",
  "Casual", "Vacation", "Festive", "Costume", "Other",
]

export const OUTFIT_PICKERS = [
  { key: "occasion", label: "Occasion", options: [
    "everyday", "work / office", "brunch", "date night", "cocktail party",
    "wedding guest", "festive / Diwali", "sangeet", "vacation", "street style", "athleisure"] },
  { key: "style", label: "Style / aesthetic", options: [
    "minimal", "classic", "boho", "streetwear", "old money", "Y2K", "edgy",
    "romantic", "Indo-western", "traditional ethnic", "contemporary ethnic"] },
  { key: "fabric", label: "Fabric", options: [
    "cotton", "linen", "silk", "satin", "chiffon", "georgette", "velvet",
    "denim", "wool", "knit", "leather", "brocade", "organza", "crepe"] },
  { key: "silhouette", label: "Silhouette", options: [
    "fitted", "tailored", "A-line", "bodycon", "oversized", "flowy",
    "wide-leg", "peplum", "mermaid", "draped", "structured"] },
  { key: "formality", label: "Formality", options: [
    "casual", "smart casual", "business", "semi-formal", "formal", "black tie", "festive"] },
  { key: "season", label: "Season", options: [
    "summer", "monsoon", "autumn", "winter", "spring", "resort"] },
]
