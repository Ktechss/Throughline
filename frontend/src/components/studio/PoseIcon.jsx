// A tiny line-silhouette for a pose, so the picker shows the pose visually.
// Poses map to a compact set of figures by keyword; stroke inherits currentColor
// so the card's selected/hover state colours the figure.

function glyphKey(id = "") {
  const s = id.toLowerCase();
  if (["headshot", "portrait", "close-up", "beauty", "three-quarter", "profile",
    "laughing", "looking-away", "chin-hand"].includes(id)) return "portrait";
  if (s.includes("selfie")) return "selfie";
  if (s.includes("walk") || s === "runway" || s === "stairs" || s === "twirl" || s === "mid-turn") return "walk";
  if (s.includes("over-shoulder") || s.includes("back-to-camera")) return "back";
  if (s.includes("reach") || s.includes("hair-touch") || s === "looking-up" || s === "long-line") return "reach";
  if (s === "arms-crossed") return "cross";
  if (s.includes("hip") || s === "triangle" || s === "power-stance" || s === "contrapposto") return "hip";
  if (s.includes("lean") || s === "against-railing") return "lean";
  if (s.startsWith("seated-floor")) return "floor";
  if (s.startsWith("seated") || s.includes("cafe")) return "sit";
  if (s.includes("kneel")) return "kneel";
  if (s.includes("crouch") || s === "squatting") return "crouch";
  if (s.includes("reclin") || s.includes("lying") || s.includes("loung")) return "recline";
  return "stand";
}

const FIGURES = {
  portrait: <><circle cx="12" cy="8.5" r="3.6" /><path d="M5 21c1.2-4.2 4-6 7-6s5.8 1.8 7 6" /></>,
  stand: <><circle cx="12" cy="4.5" r="2.3" /><path d="M12 6.8V14M12 9l-4 4.5M12 9l4 4.5M12 14l-2.6 7M12 14l2.6 7" /></>,
  walk: <><circle cx="12" cy="4.5" r="2.3" /><path d="M12 6.8V14M12 9l-3.5 3M12 9l3.5 4.5M12 14l-3.5 6.5M12 14l3.5 5" /></>,
  hip: <><circle cx="12" cy="4.5" r="2.3" /><path d="M12 6.8V14M12 9.5l-4 4M12 9.5l3.2 1.8-1 3.2M12 14l-2.4 7M12 14l2.6 7" /></>,
  cross: <><circle cx="12" cy="4.5" r="2.3" /><path d="M12 6.8V14M8.5 9.5l7 3M15.5 9.5l-7 3M12 14l-2.6 7M12 14l2.6 7" /></>,
  reach: <><circle cx="12" cy="4.8" r="2.3" /><path d="M12 7V14M12 9l4.5-4.5M12 9l-3.8 4M12 14l-2.6 7M12 14l2.6 7" /></>,
  lean: <><circle cx="10" cy="5" r="2.3" /><path d="M10 7.2l1.5 7M11.5 9.5l-3.5 3.5M11.5 9.5l3.5 2M11.5 14.2l-2 6.8M11.5 14.2l4 6.3M18 5v16" /></>,
  back: <><circle cx="12" cy="4.5" r="2.3" fill="currentColor" /><path d="M12 6.8V14M8.5 10.5h7M12 14l-2.6 7M12 14l2.6 7" /></>,
  selfie: <><circle cx="11" cy="5" r="2.3" /><path d="M11 7.2V14M11 9.5l5 -3.5M16 6l1.6 1.2M11 9.5l-3.5 3.5M11 14l-2.6 7M11 14l2.6 7" /></>,
  sit: <><circle cx="10" cy="6" r="2.3" /><path d="M10 8.2v6h6M16 14.2V21M10 10.5l-2 3.5M10 14.2l-1.5 6.8" /></>,
  floor: <><circle cx="10" cy="8" r="2.3" /><path d="M10 10.2v5M10 15.2c3 0 8 .5 10 2M10 12l-2.5 2.5" /></>,
  kneel: <><circle cx="11" cy="6" r="2.3" /><path d="M11 8.2V15M11 15l-3 4h-1M11 15l3 3v3M11 10.5l-3 3M11 10.5l3 2" /></>,
  crouch: <><circle cx="12" cy="8" r="2.3" /><path d="M12 10.2v3.5M12 13.7l-3.5 3.5-.5 3.5M12 13.7l3.5 3.5.5 3.5M12 11.5l-3 2.5M12 11.5l3 2.5" /></>,
  recline: <><circle cx="4.5" cy="13" r="2.3" /><path d="M6.8 13.5h8M14.8 13.5l4.5 2M8 13.5l1.5 3M11 13.5l1.5 3" /></>,
};

const CAT_KEY = {
  Portrait: "portrait", Standing: "stand", "Walking & Motion": "walk",
  Sitting: "sit", "Floor & Ground": "floor", "Kneeling & Crouching": "kneel",
  "Lying Down": "recline", Leaning: "lean", "Editorial & Fashion": "hip",
  "Candid & Lifestyle": "stand", "Selfie (Handheld)": "selfie", "Selfie (Mirror)": "selfie",
};

export default function PoseIcon({ id, category, className = "h-7 w-7" }) {
  const byId = glyphKey(id);
  const key = byId !== "stand" ? byId : (CAT_KEY[category] || "stand");
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {FIGURES[key] || FIGURES.stand}
    </svg>
  );
}
