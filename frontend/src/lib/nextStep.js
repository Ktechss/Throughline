// WHAT SHE NEEDS NEXT — one answer, derived in one place.
//
// This existed as scattered branches that disagreed with each other:
//
//   * the roster refused to open a `building` character but happily opened a
//     `stalled` one, straight into a studio that could not render;
//   * after locking a face, the roster sent you to `?tab=calibrate` while the
//     in-studio gate left you on `shoot` with the Generate button disabled and
//     no explanation;
//   * the backend has emitted `awaiting_face` since the multi-character work
//     (backend/main.py:195-219) and no UI branch has ever read it.
//
// Order matters: each rung is a hard prerequisite for the one below. A character
// with no master face cannot be calibrated, and an uncalibrated character can be
// photographed but every verdict comes back `ungated`, which is not a studio
// anyone wants to work in.
//
// `stats` is optional — the landing has it for the active character, the Studio
// tab dots do not. Without it the review rung is simply skipped.

export const studioUrl = (id, tab) =>
  `/studio?char=${encodeURIComponent(id)}${tab ? `&tab=${tab}` : ""}`;

/**
 * @param {object} c    a charView row (id, status, has_reference, identityStatus, job)
 * @param {object} [stats]  /api/stats for that character, if known
 * @returns {{key,label,detail,to,tone,blocked}}
 */
export function nextStep(c, stats) {
  if (!c) return { key: "none", label: "—", tone: "zinc", blocked: true };

  if (c.status === "building") {
    return {
      key: "building",
      label: "Building her…",
      // The raw backend stage is more honest than a spinner with no words.
      detail: c.job?.stage || "starting",
      tone: "sky",
      blocked: true,
    };
  }

  if (c.status === "stalled") {
    return {
      key: "stalled",
      label: "Build failed — open her",
      detail: "Her build stopped partway. Opening her shows how far it got.",
      to: studioUrl(c.id),
      tone: "rose",
      blocked: false,
    };
  }

  // NO FACE, but there are candidates waiting: `awaiting_face` is the server
  // saying exactly that. Opening her fires the mandatory picker.
  if (!c.has_reference && (c.status === "awaiting_face" || c.pending_faces > 0)) {
    return {
      key: "face",
      label: c.pending_faces
        ? `Choose her face — ${c.pending_faces} waiting`
        : "Choose her face",
      detail: "Nothing works until she has one — every shot needs the reference.",
      to: studioUrl(c.id),
      tone: "amber",
      blocked: false,
    };
  }

  // NO FACE AND NOTHING TO CHOOSE FROM. A different problem with a different
  // fix, and the one the studio used to walk straight into: its picker only
  // fires when candidates exist, so this case landed in a studio where every
  // generation 400s on the missing reference. Bio is where it is actually
  // fixable — an upload becomes her reference. Generating faces cannot help,
  // because /api/calibrate/faces refuses without a seed she does not have.
  if (!c.has_reference) {
    return {
      key: "no-face",
      label: "Upload a face for her",
      detail: "She has no master face and no candidates to choose from.",
      to: studioUrl(c.id, "bio"),
      tone: "rose",
      blocked: false,
    };
  }

  if (c.identityStatus !== "identity_set") {
    return {
      key: "calibrate",
      label: "Calibrate her",
      detail: "Until she is calibrated, every shot comes back ungated.",
      to: studioUrl(c.id, "calibrate"),
      tone: "amber",
      blocked: false,
    };
  }

  const unmarked = stats?.marks?.unmarked ?? 0;
  if (unmarked > 0) {
    return {
      key: "review",
      label: `Review ${unmarked} unmarked`,
      detail: "The gate scores her face; the body is the axis only you can judge.",
      to: studioUrl(c.id, "review"),
      tone: "zinc",
      blocked: false,
    };
  }

  return {
    key: "shoot",
    label: "Shoot",
    detail: "She is calibrated and everything is marked.",
    to: studioUrl(c.id, "shoot"),
    tone: "emerald",
    blocked: false,
  };
}

// Which studio tabs deserve an attention dot, from the same reasoning. Keeps the
// tab bar in the same order (Shoot is the daily destination) while still saying
// where the work actually is.
export function tabAttention(c, stats) {
  const step = nextStep(c, stats);
  return {
    calibrate: step.key === "calibrate",
    review: step.key === "review",
  };
}
