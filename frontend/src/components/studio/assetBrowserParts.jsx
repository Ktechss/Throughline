import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="relative mb-3">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-600" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg bg-surface ring-1 ring-line pl-8 pr-7 py-1.5 text-[12px] text-zinc-200 placeholder:text-zinc-600 focus:ring-white/30 outline-none"
      />
      {value && (
        <button onClick={() => onChange("")} className="absolute right-2 top-1/2 -translate-y-1/2">
          <X className="h-3 w-3 text-zinc-500 hover:text-zinc-300" />
        </button>
      )}
    </div>
  );
}

export function CategoryChips({ categories, active, onSelect }) {
  // Wrap so every category is visible at once — no hidden horizontal scroll.
  return (
    <div className="flex flex-wrap gap-1.5 mb-2 max-h-28 overflow-y-auto p-1">
      {categories.map((c) => (
        <button
          key={c}
          onClick={() => onSelect(c)}
          className={cn(
            "rounded-full px-2.5 py-1 text-[10px] whitespace-nowrap transition-colors ring-1",
            active === c ? "bg-white/10 text-white ring-white/15" : "text-zinc-400 ring-line hover:text-zinc-200 hover:ring-white/20"
          )}
        >
          {c}
        </button>
      ))}
    </div>
  );
}

export function CountLine({ visible, total }) {
  return (
    <div className="text-[10px] text-zinc-600 tabular-nums">
      {visible} of {total}
    </div>
  );
}

export function EmptyState({ label }) {
  return <div className="py-8 text-center text-[11px] text-zinc-600">No {label} match your search.</div>;
}