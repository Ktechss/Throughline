import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

// A FLOATING PANEL THAT CANNOT BE CLIPPED BY ITS PARENT.
//
// The roster's "..." menu was `absolute ... z-30` inside the grid at
// Landing.jsx:154, which carries `overflow-hidden`. That overflow-hidden is
// load-bearing — it is what makes `rounded-xl` clip the gap-px hairline
// dividers — so the menu was sliced off at the card edge. z-index cannot help
// with this: clipping happens during paint regardless of stacking order, and
// no z value escapes an ancestor's overflow box.
//
// The same trap has two other doors, and a plain `absolute` panel walks into
// all three:
//   * overflow-hidden / auto / scroll on any ancestor CLIPS it.
//   * transform / filter / backdrop-blur / will-change on any ancestor creates
//     a containing block, so even `position: fixed` becomes relative to that
//     ancestor rather than the viewport.
//   * opacity < 1, isolation, contain — new stacking context, z-index trapped.
//
// So the panel is PORTALLED to document.body and positioned with `fixed` from
// the trigger's own getBoundingClientRect. Nothing in the page tree is its
// ancestor any more, which makes it immune to all three by construction rather
// than by remembering to check every call site.
//
// It also flips up when there is no room below — the bug is worst on the LAST
// row of a grid, which is exactly where a downward menu has nowhere to go.

const MARGIN = 8;      // keep this far from the viewport edge

/**
 * @param open      controlled visibility
 * @param onClose   called on outside click, Escape, scroll or resize
 * @param anchorRef ref to the trigger element
 * @param align     "start" | "end" — which edge of the trigger to line up with
 */
export function Popover({ open, onClose, anchorRef, align = "end",
                          className, children }) {
  const panelRef = useRef(null);
  const [pos, setPos] = useState(null);

  const place = useCallback(() => {
    const a = anchorRef.current;
    const p = panelRef.current;
    if (!a || !p) return;
    const r = a.getBoundingClientRect();
    const { offsetWidth: pw, offsetHeight: ph } = p;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Below by default; above when the panel would not fit and there is more
    // room up there. This is the last-row case the clipping bug hid.
    const below = r.bottom + MARGIN;
    const flip = below + ph > vh - MARGIN && r.top - MARGIN - ph > MARGIN;
    const top = flip ? r.top - MARGIN - ph : below;

    let left = align === "end" ? r.right - pw : r.left;
    // Never let it hang off either edge, whatever the alignment asked for.
    left = Math.max(MARGIN, Math.min(left, vw - pw - MARGIN));

    setPos({ top: Math.max(MARGIN, top), left });
  }, [anchorRef, align]);

  // useLayoutEffect: measure and place BEFORE paint, or the panel is visible
  // for one frame at 0,0 in the corner.
  useLayoutEffect(() => {
    if (!open) { setPos(null); return; }
    place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return undefined;

    const onDown = (e) => {
      if (panelRef.current?.contains(e.target)) return;
      if (anchorRef.current?.contains(e.target)) return;   // the trigger toggles itself
      onClose?.();
    };
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    // Close rather than re-follow on scroll: a menu that tracks its trigger
    // down a scrolling list is more confusing than one that dismisses, and
    // re-measuring on every scroll frame is a jank source for no benefit.
    const onMove = () => onClose?.();

    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return createPortal(
    <div
      ref={panelRef}
      role="menu"
      style={{
        position: "fixed",
        top: pos ? pos.top : -9999,     // off-screen until measured, never at 0,0
        left: pos ? pos.left : -9999,
        // Above modal-adjacent chrome but below the modal overlay (z-50), so a
        // menu cannot float over a dialog that was opened from it.
        zIndex: 45,
      }}
      className={cn(
        "min-w-[11rem] rounded-lg bg-raised ring-1 ring-line shadow-2xl p-1",
        // Nothing to animate in until it has a measured position.
        pos ? "opacity-100" : "opacity-0",
        className,
      )}
    >
      {children}
    </div>,
    document.body,
  );
}

export default Popover;
