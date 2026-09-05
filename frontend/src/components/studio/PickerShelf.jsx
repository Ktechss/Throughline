import React, { useEffect, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";

// THREE BIG PICKERS THAT DO NOT ALL NEED TO BE OPEN.
//
// Outfit, Pose and Nails each render a search box, ~20 category chips and a
// twelve-tile grid. Stacked and always expanded they ran the right rail past
// 4,000px, so choosing a pose meant scrolling the whole wardrobe first.
//
// The reason this can collapse when the Camera & finish group also collapses is
// that nobody compares an outfit *against* a pose — you pick one of each. What
// you must never lose is WHICH one you picked, and that is the failure mode of
// naive accordions: state hidden behind a closed lid. So the header carries the
// selection — thumbnail and name — and reads the same closed as open. Closing a
// section here hides the options, never the answer.
//
// Open/closed is remembered per shelf, because "collapse the wardrobe" is a
// working preference, not a per-visit decision.

const KEY = "tl.shelf.";

export default function PickerShelf({
  id, title, icon: Icon, selected, thumb, onClear, children, defaultOpen = false,
}) {
  // A caller that hands us the selected ROW instead of its name renders an
  // object as a React child, which unmounts the whole tab — the shelf goes
  // blank and takes the page with it. Name the row rather than crash on it.
  const label = selected && typeof selected === "object"
    ? (selected.name || selected.label || selected.id || null)
    : selected;

  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem(KEY + id);
      return v === null ? defaultOpen : v === "1";
    } catch { return defaultOpen; }
  });
  useEffect(() => {
    try { localStorage.setItem(KEY + id, open ? "1" : "0"); } catch { /* private mode */ }
  }, [id, open]);

  return (
    <section className="rounded-xl bg-surface ring-1 ring-line-subtle overflow-hidden">
      <div className="flex items-center gap-2.5 px-3.5 py-2.5">
        <button onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
          aria-expanded={open}>
          {Icon && <Icon className="h-3.5 w-3.5 shrink-0 text-ink-subtle" />}
          <span className="text-[13px] font-medium text-ink shrink-0">{title}</span>

          {/* The selection, legible with the shelf shut. */}
          {label ? (
            <span className="flex min-w-0 items-center gap-1.5">
              {thumb && (
                <img src={thumb} alt="" className="h-5 w-5 shrink-0 rounded object-cover ring-1 ring-line" />
              )}
              <span className="truncate text-[13px] text-ink-muted">{label}</span>
            </span>
          ) : (
            <span className="text-[13px] text-ink-faint">none</span>
          )}

          <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-ink-subtle transition-transform",
            open && "rotate-180")} />
        </button>

        {/* Clearing is a sibling of the toggle, not nested inside it — a button
            cannot contain a button, and this one must work with the shelf shut. */}
        {label && onClear && (
          <button onClick={onClear} aria-label={`Clear ${title.toLowerCase()}`}
            className="shrink-0 rounded p-1 text-ink-faint hover:text-ink hover:bg-raised">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {open && <div className="border-t border-line-subtle p-3.5 pt-3">{children}</div>}
    </section>
  );
}
