import React, { useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

// One modal, instead of nine.
//
// Every overlay in this app hand-rolled the same three things — a fixed backdrop,
// a panel that stops mousedown from reaching it, and a header with a close
// button — and each got a slightly different z-index, blur, radius and max
// height. They also all missed the same two behaviours, because you only notice
// them when they are absent: Escape did not close anything, and the page behind
// kept scrolling under the overlay.
//
// `size="drawer"` is the right-hand sheet OutfitDrawer needs; everything else is
// a centred panel.

export function Modal({
  open = true,
  onClose,
  title,
  subtitle,
  footer,
  size = "md",
  children,
  className,
  closeOnBackdrop = true,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    // The page behind an overlay must not scroll with the wheel — restored on
    // unmount rather than set blindly, so nested modals cannot strand it.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const drawer = size === "drawer";
  const width = { sm: "max-w-[420px]", md: "max-w-[560px]", lg: "max-w-[780px]",
                  xl: "max-w-5xl" }[size] || "max-w-[560px]";

  return (
    <div
      className={cn("fixed inset-0 z-50 flex p-4",
        drawer ? "justify-end items-stretch" : "items-center justify-center")}
      onMouseDown={closeOnBackdrop ? onClose : undefined}
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === "string" ? title : undefined}
    >
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className={cn(
          "relative flex flex-col overflow-hidden bg-[#0d0d0f] ring-1 ring-line shadow-2xl",
          "animate-in fade-in duration-150",
          drawer
            ? "h-full w-full max-w-[480px] rounded-2xl slide-in-from-right-4"
            : cn("w-full max-h-[88vh] rounded-2xl zoom-in-95", width),
          className,
        )}
      >
        {(title || onClose) && (
          <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/10 shrink-0">
            <div className="min-w-0">
              {title && (
                <div className="text-[13px] font-semibold text-zinc-100">{title}</div>
              )}
              {subtitle && (
                <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{subtitle}</div>
              )}
            </div>
            {onClose && (
              <button onClick={onClose} aria-label="Close"
                className="shrink-0 rounded-md p-1 text-zinc-500 hover:text-zinc-100 hover:bg-white/5">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>

        {footer && (
          <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-white/10 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// The two buttons every footer needs, so they stop being re-styled per file.
export function Button({ variant = "ghost", className, ...props }) {
  const styles = {
    primary: "bg-white text-black hover:bg-zinc-200",
    danger: "bg-rose-600 text-white hover:bg-rose-500",
    ghost: "text-zinc-400 hover:text-zinc-100 hover:bg-white/5",
    outline: "text-zinc-200 ring-1 ring-white/15 hover:ring-white/30 hover:bg-white/5",
  }[variant];
  return (
    <button
      className={cn(
        "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] font-medium",
        "transition-colors disabled:opacity-40 disabled:pointer-events-none",
        styles, className,
      )}
      {...props}
    />
  );
}

export default Modal;
