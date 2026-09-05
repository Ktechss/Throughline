import React, { useRef } from "react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

// The selected-pill. `"bg-white text-black ring-white"` was written out by hand
// in seven files, and Landing defined its own helper then bypassed it with four
// inline copies at four different radii.
//
// `Chip` on its own is a plain button — that is what the Review filters want.
// `ChipRow` is the accessible single-select: a real radio group.

export const Chip = React.forwardRef(function Chip(
  { selected, onClick, children, className, title, role, tabIndex, ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      title={title}
      role={role}
      tabIndex={tabIndex}
      aria-checked={role === "radio" ? !!selected : undefined}
      className={cn(
        // 26px tall, not 22: WCAG 2.2 SC 2.5.8 wants a 24px target, and the old
        // py-1 chip only passed via the spacing exception — on the line rather
        // than over it.
        "inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[12px] ring-1",
        "transition-colors outline-none focus-visible:ring-2 focus-visible:ring-white/60",
        selected
          ? "bg-white text-black ring-white"
          // ring-white/10 on near-black is ~1.3:1 and fails SC 1.4.11's 3:1 for
          // a component boundary — if the ring is the only thing saying "this is
          // a control", it has to be visible.
          : "text-zinc-300 ring-white/25 hover:ring-white/45",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

/**
 * Single-select chips as a RADIO GROUP.
 *
 * The old version was twelve unrelated `<button>`s: a screen-reader user heard
 * twelve controls with no indication that they were alternatives or which one
 * was active, and there was no way to move between them but Tab, twelve times.
 *
 * It also hid its only "un-choose" affordance. The comment admitted it —
 * clicking the selected chip cleared it, "there is otherwise no way to
 * un-choose" — which is an invisible gesture guarding the app's most important
 * default. Now AUTO IS THE FIRST CHIP: selected whenever nothing else is, so
 * the default is visible, reachable by keyboard, and un-choosing is just
 * choosing something else. That also makes this a legitimate radio group, which
 * cannot express "nothing checked".
 *
 * Keyboard follows the ARIA APG radio pattern: one Tab stop for the whole
 * group (roving tabindex), arrows move AND select, wrapping at both ends.
 */
export function ChipRow({
  options = [], value, onChange, className, label,
  auto = true, autoLabel = "Auto",
}) {
  const refs = useRef([]);
  const items = [
    ...(auto ? [{ value: null, label: autoLabel, isAuto: true }] : []),
    ...options.map((o) => (typeof o === "string"
      ? { value: o, label: o }
      : { value: o.value, label: o.label ?? o.value })),
  ];
  const current = Math.max(0, items.findIndex((o) => o.value === (value ?? null)));

  const move = (delta) => {
    const next = (current + delta + items.length) % items.length;
    onChange(items[next].value);
    refs.current[next]?.focus();
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
  };

  return (
    <div role="radiogroup" aria-label={label}
      onKeyDown={onKeyDown}
      className={cn("flex flex-wrap gap-2", className)}>
      {items.map((o, i) => (
        <Chip
          key={o.value ?? "__auto"}
          ref={(el) => { refs.current[i] = el; }}
          role="radio"
          selected={i === current}
          // One Tab stop: focus enters at the selected chip and arrows do the
          // rest, rather than tabbing through every option in every row.
          tabIndex={i === current ? 0 : -1}
          onClick={() => onChange(o.value)}
          className={cn(o.isAuto && i !== current && "text-ink-subtle")}
        >
          {o.isAuto && <Sparkles className="h-3 w-3 opacity-70" />}
          {o.label}
        </Chip>
      ))}
    </div>
  );
}

export default ChipRow;
