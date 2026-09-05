import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// A collapsible group with a "how much of this have I filled in" badge.
//
// Six files each rolled their own version of this (Landing, PosePicker,
// OutfitPicker, ReviewTab, collab/BrowsePicker, collab/CastRow), every one of
// them importing ChevronDown and writing the same rotate-180.
//
// `count`/`total` render as "N of M set", falling back to the app's standing
// promise for anything left blank. Landing's copy had to fudge that badge with a
// hardcoded `+ 1` because two of its values lived outside the object it counted;
// counting is done by the caller here, from one source.

export function Section({
  title, count, total, hint, defaultOpen = false, children, className,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const badge = total != null
    ? (count ? `${count} of ${total} set` : hint || "Claude decides")
    : null;

  return (
    <div className={cn("rounded-xl ring-1 ring-line-subtle bg-surface", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 text-left"
      >
        <span className="text-[12px] font-medium text-zinc-200">{title}</span>
        <span className="flex items-center gap-2">
          {badge && <span className="text-[10px] text-zinc-500">{badge}</span>}
          <ChevronDown
            className={cn("h-3.5 w-3.5 text-zinc-500 transition-transform",
              open && "rotate-180")}
          />
        </span>
      </button>
      {open && <div className="px-3.5 pb-3.5 space-y-3">{children}</div>}
    </div>
  );
}

export default Section;
