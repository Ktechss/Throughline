import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, Loader2, MoreHorizontal, Pencil, Plus, ShieldAlert, ShieldCheck, Trash2,
} from "lucide-react";
import { confirm, promptText } from "@/components/ui/confirm";
import { Popover } from "@/components/ui/popover";
import { toast } from "@/components/ui/use-toast";
import { api, setApiCharacter, charView, runView } from "@/api/throughline";
import { nextStep, studioUrl } from "@/lib/nextStep";
import { cn } from "@/lib/utils";

// WHERE SHE IS, AND WHAT TO DO NEXT.
//
// This was a marketing hero ("One face. / Hundreds of shots. / Zero drift.")
// over a grid of cards carrying a name and a status dot, for a roster with one
// person in it — a pitch, on a single-user local tool, above a control surface
// that said nothing about the character it was picking.
//
// It is now a dashboard: her state, the one thing worth doing, her numbers, and
// her actual work. A tool for making images that showed no images was the
// clearest sign the page was laid out by habit rather than by purpose.
//
// SCOPING: every request passes `?character=<id>` explicitly and NOTHING calls
// setApiCharacter. The roster is not "inside" anyone, and pinning the module
// global here is how one character's data ends up under another's name. An
// <img> cannot send the header at all, which is why the thumbnails carry it too.

export default function Landing() {
  const navigate = useNavigate();
  const [chars, setChars] = useState(null);      // null = not loaded yet
  const [active, setActive] = useState(null);
  const [stats, setStats] = useState(null);
  const [gallery, setGallery] = useState(null);
  const [recent, setRecent] = useState([]);
  const [err, setErr] = useState(null);
  const [menu, setMenu] = useState(null);

  const load = async () => {
    try {
      const r = await api.get("/api/characters");
      setChars((r.characters || []).map(charView));
      setActive(r.active);
    } catch (e) { setErr(String(e)); setChars([]); }
  };
  useEffect(() => { setApiCharacter(null); load(); }, []);

  // Her numbers and her last few frames — for the ACTIVE character only.
  // /api/stats carries per-pose and per-outfit breakdowns and runs to ~16 KB;
  // fanning that across a roster spends all of it to render a name and a badge,
  // which /api/characters already answers.
  useEffect(() => {
    if (!active) return;
    const q = `?character=${encodeURIComponent(active)}`;
    api.get(`/api/stats${q}`).then(setStats).catch(() => setStats(null));
    api.get(`/api/gallery${q}`).then(setGallery).catch(() => setGallery(null));
    api.get(`/api/runs${q}`)
      .then((d) => setRecent(((d.runs || d || []).slice(0, 16)).map(runView)))
      .catch(() => setRecent([]));
  }, [active]);

  const building = (chars || []).some((c) => c.status === "building");
  useEffect(() => {
    if (!building) return undefined;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [building]);

  const me = (chars || []).find((c) => c.id === active) || (chars || [])[0] || null;
  const others = (chars || []).filter((c) => c.id !== me?.id);

  const open = async (c, tab) => {
    if (c.status === "building") return;
    try { await api.send("/api/characters/active", "PUT", { id: c.id }); } catch { /* studio re-sets it */ }
    navigate(tab ? studioUrl(c.id, tab) : (nextStep(c).to || studioUrl(c.id)));
  };

  const rename = async (c) => {
    setMenu(null);
    const name = await promptText({ title: "Rename character", defaultValue: c.name, confirmLabel: "Rename" });
    if (!name || name === c.name) return;
    try { await api.send(`/api/characters/${c.id}`, "PUT", { name }); await load(); toast.ok("Renamed"); }
    catch (e) { setErr(String(e)); }
  };

  const remove = async (c) => {
    setMenu(null);
    if (!(await confirm({
      title: `Delete "${c.name}"?`,
      body: "Her images, wardrobe, references and every generation go with her. "
          + "Back her up from Settings first if you might want her again.",
      confirmLabel: "Delete her", danger: true,
    }))) return;
    try { await api.send(`/api/characters/${c.id}`, "DELETE"); await load(); toast.ok(`Deleted ${c.name}`); }
    catch (e) { setErr(String(e)); }
  };

  return (
    <div className="px-6 py-6 max-w-[1600px]">
      <header className="flex items-end justify-between gap-4 mb-8">
        <h1 className="text-[24px] font-semibold tracking-[-0.4px] leading-none text-ink">
          Characters
        </h1>
        <Link to="/characters/new"
          className="inline-flex h-8 items-center gap-2 rounded-md bg-white text-black px-3 text-[13px] font-medium hover:bg-zinc-200">
          <Plus className="h-3.5 w-3.5" /> New character
        </Link>
      </header>

      {err && (
        <button onClick={() => setErr(null)}
          className="w-full text-left mb-6 rounded-lg bg-rose-500/10 ring-1 ring-rose-500/30 px-3 py-2 text-[13px] text-rose-300">
          {err}
        </button>
      )}

      {chars === null && <Skeleton />}
      {chars !== null && chars.length === 0 && <Empty />}

      {me && (
        <div className="space-y-8">
          <Hero c={me} stats={stats} gallery={gallery}
            onOpen={(tab) => open(me, tab)}
            onRename={() => rename(me)} onRemove={() => remove(me)}
            canDelete={chars.length > 1} menu={menu === me.id}
            onMenu={() => setMenu(menu === me.id ? null : me.id)} />

          {recent.length > 0 && (
            <section>
              <SectionHead title="Recent shots"
                action={<button onClick={() => open(me, "review")}
                  className="text-[13px] text-ink-subtle hover:text-ink">Review all →</button>} />
              <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 2xl:grid-cols-12 gap-3">
                {recent.map((r) => (
                  <button key={r.id} onClick={() => open(me, "review")}
                    title={`sim ${r.similarity ?? "—"} · ${r.status || "ungated"}`}
                    className="group relative aspect-[3/4] overflow-hidden rounded-md bg-surface ring-1 ring-line-subtle hover:ring-line-strong transition">
                    <img src={`${r.thumb}?character=${encodeURIComponent(me.id)}`} alt=""
                      loading="lazy"
                      className="h-full w-full object-cover transition group-hover:scale-[1.03]" />
                    {r.similarity != null && (
                      <span className="tnum absolute bottom-1 left-1 rounded bg-black/70 px-1 py-0.5 text-[10px] text-white/90">
                        {Number(r.similarity).toFixed(2)}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </section>
          )}

          {others.length > 0 && (
            <section>
              <SectionHead title="Everyone else" />
              <div className="grid gap-px sm:grid-cols-2 xl:grid-cols-3 rounded-xl bg-line-subtle ring-1 ring-line-subtle overflow-hidden [&>*]:bg-surface">
                {others.map((c) => (
                  <Row key={c.id} c={c} onOpen={() => open(c)}
                    onRename={() => rename(c)} onRemove={() => remove(c)}
                    canDelete={chars.length > 1}
                    menu={menu === c.id} onMenu={() => setMenu(menu === c.id ? null : c.id)} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- pieces

// 15px/600. The app had ~400 pieces of text between 9 and 13px and eleven above
// it, so nothing could be a heading — this is the missing rung.
function SectionHead({ title, action }) {
  return (
    <div className="flex items-baseline justify-between gap-4 mb-3">
      <h2 className="text-[15px] font-semibold tracking-[-0.1px] text-ink">{title}</h2>
      {action}
    </div>
  );
}

function Badge({ c }) {
  if (c.status === "building") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-sky-500/10 ring-1 ring-sky-500/30 px-2 py-0.5 text-[11px] text-sky-300">
        <Loader2 className="h-3 w-3 animate-spin" /> {c.job?.stage || "building"}
      </span>
    );
  }
  const bad = c.status === "stalled" || !c.has_reference;
  const ok = !bad && c.identityStatus === "identity_set";
  const tone = bad ? "text-rose-300 ring-rose-500/30 bg-rose-500/10"
    : ok ? "text-emerald-300 ring-emerald-500/30 bg-emerald-500/10"
    : "text-amber-300 ring-amber-500/30 bg-amber-500/10";
  const label = c.status === "stalled" ? "build failed"
    : !c.has_reference ? "no face" : ok ? "identity set" : "needs calibration";
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ring-1", tone)}>
      <Icon className="h-3 w-3" /> {label}
    </span>
  );
}

function Avatar({ c, className = "h-14 w-14" }) {
  return (
    <div className={cn(className, "shrink-0 rounded-lg overflow-hidden bg-raised ring-1 ring-line-subtle flex items-center justify-center")}>
      {c.avatar
        ? <img src={c.avatar} alt="" className="h-full w-full object-cover" />
        : <span className="text-[13px] font-medium text-ink-faint">{c.initials}</span>}
    </div>
  );
}

// The panel is PORTALLED (see ui/popover.jsx). It used to be a plain
// `absolute ... z-30` child, and the roster grid above carries overflow-hidden
// to make rounded-xl clip its gap-px hairlines — so the menu was sliced off at
// the card edge. z-index cannot escape an ancestor's clip; only leaving the
// subtree can.
function Menu({ open, onMenu, onRename, onRemove, canDelete }) {
  const btn = useRef(null);
  return (
    <div className="shrink-0">
      <button ref={btn} onClick={onMenu} aria-label="More"
        aria-haspopup="menu" aria-expanded={open}
        className="grid h-8 w-8 place-items-center rounded-md text-ink-subtle hover:text-ink hover:bg-raised">
        <MoreHorizontal className="h-4 w-4" />
      </button>
      <Popover open={open} onClose={onMenu} anchorRef={btn} align="end">
        <button role="menuitem" onClick={onRename}
          className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-muted hover:bg-selected">
          <Pencil className="h-3.5 w-3.5" /> Rename
        </button>
        <button role="menuitem" onClick={canDelete ? onRemove : undefined} disabled={!canDelete}
          title={canDelete ? undefined : "The last character cannot be deleted"}
          className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-rose-300 hover:bg-rose-500/10 disabled:opacity-40 disabled:hover:bg-transparent">
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </button>
      </Popover>
    </div>
  );
}

function Hero({ c, stats, gallery, onOpen, onRename, onRemove, canDelete, menu, onMenu }) {
  const step = nextStep(c, stats);
  const angles = gallery?.entries?.length ?? 0;
  const kept = stats?.gate?.kept ?? 0;
  const total = stats?.total ?? 0;

  return (
    <section className="space-y-4">
      <div className="flex items-start gap-4">
        <Avatar c={c} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h2 className="text-[24px] font-semibold tracking-[-0.4px] leading-none text-ink truncate">
              {c.name}
            </h2>
            <Badge c={c} />
          </div>
          <div className="tnum mt-2 text-[13px] text-ink-faint">
            {gallery?.threshold != null && <>threshold {gallery.threshold} · </>}
            {angles} gallery {angles === 1 ? "angle" : "angles"}
          </div>
        </div>
        <Menu open={menu} onMenu={onMenu} onRename={onRename} onRemove={onRemove}
          canDelete={canDelete} />
      </div>

      {/* The one thing worth doing, stated rather than inferred from a badge. */}
      <div className={cn("flex items-center gap-4 rounded-xl px-4 py-3.5 ring-1",
        step.tone === "rose" ? "bg-rose-500/[0.07] ring-rose-500/25"
          : step.tone === "amber" ? "bg-amber-500/[0.07] ring-amber-500/25"
          : step.tone === "sky" ? "bg-sky-500/[0.07] ring-sky-500/25"
          : "bg-surface ring-line-subtle")}>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-ink">{step.label}</div>
          {step.detail && <div className="text-[13px] text-ink-subtle mt-0.5">{step.detail}</div>}
        </div>
        {step.blocked
          ? <Loader2 className="h-4 w-4 animate-spin text-sky-300 shrink-0" />
          : (
            <button onClick={() => onOpen()}
              className="shrink-0 inline-flex h-9 items-center gap-1.5 rounded-md bg-white text-black px-3.5 text-[13px] font-medium hover:bg-zinc-200">
              Open {c.name} <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
      </div>

      {/* ONE surface with five cells, not five detached cards. Five equal boxes
          asserts five equally-important numbers; these are one ratio and its
          parts, so keep-rate carries the colour and unmarked is a backlog you
          can click, not a statistic. */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 rounded-xl bg-surface ring-1 ring-line-subtle divide-x divide-line-subtle overflow-hidden">
          <Stat label="Shots" value={total} context="all time" />
          <Stat label="Keep-rate" value={`${Math.round((stats.gate?.keep_rate ?? 0) * 100)}%`}
            context={`${kept} of ${total} past the gate`} accent="text-emerald-400" />
          <Stat label="Approved" value={stats.marks?.approved ?? 0} context="you marked these" />
          <Stat label="Unmarked" value={stats.marks?.unmarked ?? 0} context="waiting on you"
            accent="text-amber-400" onClick={() => onOpen("review")} />
          <Stat label="Gold set" value={stats.gold_set ?? 0} context="the curated set" />
        </div>
      )}
    </section>
  );
}

// Label ABOVE value: the eye lands on the number and only reads up for meaning
// if it needs to. The context line is what turns "51%" from a figure into a
// fact you can act on.
function Stat({ label, value, context, accent, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick}
      className={cn("px-5 py-4 text-left", onClick && "hover:bg-raised transition-colors")}>
      <div className="text-[11px] font-medium uppercase tracking-[0.02em] text-ink-subtle">
        {label}
      </div>
      <div className={cn("tnum mt-1.5 text-[28px] font-semibold leading-none", accent || "text-ink")}>
        {value}
      </div>
      {context && <div className="mt-1.5 text-[11px] text-ink-faint">{context}</div>}
    </Tag>
  );
}

function Row({ c, onOpen, onRename, onRemove, canDelete, menu, onMenu }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <button onClick={onOpen} disabled={c.status === "building"}
        className="flex min-w-0 flex-1 items-center gap-3 text-left disabled:cursor-default">
        <Avatar c={c} className="h-9 w-9" />
        <span className="min-w-0">
          <span className="block text-[13px] font-medium text-ink truncate">{c.name}</span>
          <span className="mt-1 block"><Badge c={c} /></span>
        </span>
      </button>
      <Menu open={menu} onMenu={onMenu} onRename={onRename} onRemove={onRemove}
        canDelete={canDelete} />
    </div>
  );
}

// Mirrors the real layout rather than showing a generic frame — NN/G's point is
// that a skeleton which does not match what arrives is just a spinner that
// takes up more room.
function Skeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="h-14 w-14 rounded-lg bg-surface" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-6 w-48 rounded bg-surface" />
          <div className="h-3 w-64 rounded bg-surface/70" />
        </div>
      </div>
      <div className="h-16 rounded-xl bg-surface" />
      <div className="grid grid-cols-5 rounded-xl bg-surface h-[92px]" />
      <div className="grid grid-cols-8 gap-3">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="aspect-[3/4] rounded-md bg-surface" />
        ))}
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="rounded-xl bg-surface ring-1 ring-line-subtle px-6 py-14 text-center">
      <h2 className="text-[15px] font-semibold text-ink">No characters yet</h2>
      <p className="mx-auto mt-2 max-w-[440px] text-[13px] text-ink-subtle leading-relaxed">
        A character is a bio, one master face, and a calibrated gallery that every
        later shot is scored against. That gallery is what makes hundreds of images
        the same woman.
      </p>
      <Link to="/characters/new"
        className="mt-6 inline-flex h-9 items-center gap-2 rounded-md bg-white text-black px-4 text-[13px] font-medium hover:bg-zinc-200">
        <Plus className="h-3.5 w-3.5" /> Create your first character
      </Link>
    </div>
  );
}
