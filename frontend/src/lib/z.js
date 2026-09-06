// ONE LADDER, WRITTEN DOWN.
//
// There were eleven z-index values across eight files and none of them knew
// about the others. That is how ReviewTab's per-tile checkbox (z-10, escaping
// a z-auto `relative` parent into the ROOT stacking context) ended up tying
// its own sticky filter bar (also z-10) and winning on document order — so
// checkboxes painted over the Unmarked/All/Approved chips while scrolling.
//
// Two rules keep this list short and keep it true:
//
//   1. A card that stacks its own overlays wears `isolate`. Its badges then
//      live at `tile` INSIDE the card and never reach this ladder at all.
//   2. Anything that must float over the page goes through <Layer> and takes a
//      rung from here — never a literal.
//
// The gap between popover and modal is deliberate: a dialog opened FROM a menu
// must never be painted under the menu that opened it.
export const Z = {
  tile: 1,       // inside a card that isolates: badges, checkboxes, gradients
  sticky: 20,    // in-page sticky chrome: tab strip, filter bar, bulk bar
  nav: 30,       // app chrome: sidebar, mobile top bar
  popover: 45,   // menus and dropdowns
  modal: 50,
  toast: 100,
};

// Tailwind scans source text LITERALLY, so a class name built at runtime is
// never emitted into the stylesheet. These exist so the scanner can see them;
// prefer the numeric Z above in inline styles.
export const ZC = {
  tile: "z-[1]",
  sticky: "z-20",
  nav: "z-30",
  popover: "z-[45]",
  modal: "z-50",
  toast: "z-[100]",
};
