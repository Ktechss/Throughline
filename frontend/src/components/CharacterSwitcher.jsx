import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronsUpDown, Plus, ShieldAlert, ShieldCheck, Loader2 } from "lucide-react";
import { api, charView } from "@/api/throughline";
import { nextStep, studioUrl } from "@/lib/nextStep";
import { cn } from "@/lib/utils";
import { Popover } from "@/components/ui/popover";

// WHO YOU ARE WORKING ON, and how to change it — from anywhere.
//
// Until now the app had exactly one character switcher: a 12px zinc-500 "Switch
// character" link at the top of the Studio (Studio.jsx:116-118) that navigated
// back to the roster. On /settings and /collaborate there was no indication of
// the active character at all, even though the backend holds one and every
// unscoped request silently uses it.
//
// Two mounts, one component: the sidebar footer (where a fake "Director / studio
// mode" chip used to sit) and the in-character header.

export default function CharacterSwitcher({ variant = "sidebar", activeId, onPick }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [active, setActive] = useState(activeId || null);
  const box = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();

  const load = () =>
    api.get("/api/characters")
      .then((d) => {
        setRows((d.characters || []).map(charView));
        setActive((cur) => activeId || d.active || cur);
      })
      .catch(() => {});

  useEffect(() => { load(); }, []);
  useEffect(() => { if (activeId) setActive(activeId); }, [activeId]);

  // Outside-click and Escape belong to Popover now. A copy here would be
  // actively wrong: the panel is portalled to document.body, so it is no longer
  // inside `box`, and `!box.contains(target)` would fire on mousedown over a
  // menu item and close the panel before its click could land.

  const cur = rows.find((r) => r.id === active);

  // Where switching lands you. If she needs something — a face, calibration —
  // go there; the alternative is dropping the user on a Shoot tab whose Generate
  // button is disabled for reasons nothing on screen explains. If she is ready,
  // keep the tab you were already on, because switching characters is not a
  // request to change what you were doing.
  const pick = (c) => {
    setOpen(false);
    if (onPick) { onPick(c); return; }
    const step = nextStep(c);
    if (step.blocked) return;
    const currentTab = new URLSearchParams(location.search).get("tab");
    const keepTab = step.key === "shoot" && currentTab;
    navigate(keepTab ? studioUrl(c.id, currentTab) : (step.to || studioUrl(c.id)));
  };

  const Badge = ({ c }) => {
    if (c.status === "building") return <Loader2 className="h-3 w-3 animate-spin text-sky-400" />;
    if (!c.has_reference || c.status === "stalled") return <ShieldAlert className="h-3 w-3 text-rose-400" />;
    if (c.identityStatus === "identity_set") return <ShieldCheck className="h-3 w-3 text-emerald-400" />;
    return <ShieldAlert className="h-3 w-3 text-amber-400" />;
  };

  const Avatar = ({ c, size = "h-8 w-8" }) => (
    <div className={cn(size, "shrink-0 rounded-full overflow-hidden bg-zinc-800 ring-1 ring-line flex items-center justify-center")}>
      {c?.avatar
        ? <img src={c.avatar} alt="" className="h-full w-full object-cover" />
        : <span className="text-[11px] font-medium text-zinc-400">{c?.initials || "?"}</span>}
    </div>
  );

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "w-full flex items-center gap-2.5 rounded-lg transition-colors",
          variant === "sidebar"
            ? "px-3 py-2 hover:bg-white/[0.04]"
            : "px-2.5 py-1.5 ring-1 ring-line hover:ring-white/25 bg-surface",
        )}
      >
        <Avatar c={cur} size={variant === "sidebar" ? "h-8 w-8" : "h-6 w-6"} />
        <span className="min-w-0 flex-1 text-left leading-tight">
          <span className="block text-[12px] font-medium text-zinc-100 truncate">
            {cur?.name || "No character"}
          </span>
          {variant === "sidebar" && (
            <span className="block text-[10px] text-zinc-500 truncate">
              {cur ? (cur.identityStatus === "identity_set" ? "identity set" : "needs calibration")
                   : "pick one to begin"}
            </span>
          )}
        </span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      </button>

      {/* Portalled for the same reason as the roster menu: this renders in the
          sidebar footer and in the Studio header, and neither call site can
          promise it has no clipping or transformed ancestor. `absolute` here
          was working by luck, not by design. Popover keeps the outside-click
          and Escape handling this component already had. */}
      <Popover open={open} onClose={() => setOpen(false)} anchorRef={box}
        align="start"
        className="w-[240px] rounded-xl bg-[#141417] p-1.5">
        <div>
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-[0.16em] text-zinc-600">
            Characters
          </div>
          <div className="max-h-[280px] overflow-y-auto">
            {rows.map((c) => (
              <button
                key={c.id}
                onClick={() => pick(c)}
                disabled={c.status === "building"}
                className={cn(
                  "w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors",
                  c.id === active ? "bg-white/[0.07]" : "hover:bg-white/[0.04]",
                  c.status === "building" && "opacity-50 cursor-default",
                )}
              >
                <Avatar c={c} size="h-6 w-6" />
                <span className="min-w-0 flex-1 text-[12px] text-zinc-200 truncate">{c.name}</span>
                <Badge c={c} />
              </button>
            ))}
          </div>
          <div className="mt-1 border-t border-white/5 pt-1">
            <button
              onClick={() => { setOpen(false); navigate("/characters/new"); }}
              className="w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[12px] text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04]"
            >
              <Plus className="h-3.5 w-3.5" /> New character
            </button>
          </div>
        </div>
      </Popover>
    </div>
  );
}
