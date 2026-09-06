import { createPortal } from "react-dom";

// THE ONE DOOR OUT OF THE TREE.
//
// A floating element's geometry and paint order are decided by its ANCESTORS,
// and this app has three separate ancestors that decide them wrongly. No
// z-index fixes any of the three:
//
//   1. overflow-hidden | auto | scroll  -> CLIPS the panel, at any z-index.
//      Landing.jsx's roster grid is the case: its overflow-hidden is
//      load-bearing (it is what makes rounded-xl clip the gap-px hairlines),
//      and it sliced the row menu in half.
//
//   2. transform | filter | backdrop-blur | will-change | contain
//      -> becomes the CONTAINING BLOCK, so even `position: fixed` re-anchors
//      to that ancestor instead of the viewport.
//
//   3. position:sticky | opacity<1 | isolation
//      -> new STACKING CONTEXT, so z-index resolves locally and cannot compete
//      with the ancestor's siblings. ShootTab's `xl:sticky` rail is why a z-50
//      modal opened from the Nails shelf painted UNDER the z-20 tab strip --
//      but only above 1280px, which is what made it look intermittent.
//
// Leaving the subtree fixes all three at once, by construction rather than by
// remembering to audit every ancestor at every call site. CLAUDE.md's spine
// says never add a step a human has to eyeball; "check the ancestors for
// overflow/transform/sticky before mounting a dialog" is exactly that step.
//
// Everything that must float over the page goes through here. Nothing else
// needs to know why.
export function Layer({ children }) {
  if (typeof document === "undefined") return null;   // SSR / test renderer
  return createPortal(children, document.body);
}

export default Layer;
