import { refUrl, apiCharacter } from "@/api/throughline";
import React, { useState } from "react";
import { Lock, Star, Upload, Trash2, RefreshCw, ImageOff, ImagePlus, X, LoaderCircle, Home, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { promptText } from "@/components/ui/confirm";

const SUBVIEWS = ["overview", "home", "advanced · body", "advanced · parts"];

export default function BioTab({
  bio,
  gallery,
  refs,
  bodies,
  parts,
  hasIdentity,
  bodyPreview,
  bodyBusy,
  onSetBio,
  onDeleteRef,
  onToGallery,
  onImport,
  onUploadRef,
  onSavePart,
  onResetParts,
  onUploadShape,
  onCreateBody,
  onSaveBody,
  onDiscardBody,
  onSelectBody,
  onDeleteBody,
  home,
  homeBusy,
  onSaveHome,
  onUploadCorner,
  onGenerateCorner,
  onDeleteCorner,
}) {
  const [sub, setSub] = useState("overview");

  const safeBio = bio || { reference: null, body_reference: null, calib_seed: null };
  const safeGallery = gallery || { entries: [], threshold: null };
  const safeRefs = refs || [];
  const safeBodies = bodies || { bodies: [], active: null };
  const safeParts = parts || [];

  return (
    <div>
      <div className="flex items-center gap-1 mb-6 flex-wrap">
        {SUBVIEWS.map((s) => (
          <button
            key={s}
            onClick={() => setSub(s)}
            className={cn(
              "rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors",
              sub === s ? "bg-white text-black" : "ring-1 ring-line text-zinc-400 hover:text-white"
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {sub === "overview" && (
        <Overview
          bio={safeBio} gallery={safeGallery} parts={safeParts} hasIdentity={hasIdentity}
          refs={safeRefs} onSetBio={onSetBio} onDeleteRef={onDeleteRef}
          onToGallery={onToGallery} onImport={onImport} onUploadRef={onUploadRef}
        />
      )}
      {sub === "advanced · body" && (
        <AdvancedBody
          bodies={safeBodies}
          bodyPreview={bodyPreview}
          bodyBusy={bodyBusy}
          onUploadShape={onUploadShape}
          onCreateBody={onCreateBody}
          onSaveBody={onSaveBody}
          onDiscardBody={onDiscardBody}
          onSelectBody={onSelectBody}
          onDeleteBody={onDeleteBody}
        />
      )}
      {sub === "home" && (
        <HomeSection
          home={home || { style: "", surroundings: "", corners: [] }} busy={homeBusy || {}}
          onSaveHome={onSaveHome} onUpload={onUploadCorner}
          onGenerate={onGenerateCorner} onDelete={onDeleteCorner}
        />
      )}
      {sub === "advanced · parts" && <AdvancedParts parts={safeParts} onSavePart={onSavePart} onResetParts={onResetParts} />}
    </div>
  );
}

/* ---------------- Home (her house, part of the BIO) ---------------- */

function HomeSection({ home, busy, onSaveHome, onUpload, onGenerate, onDelete }) {
  const [style, setStyle] = useState(home.style || "");
  const [surroundings, setSurroundings] = useState(home.surroundings || "");
  const [stamp, setStamp] = useState(0);   // cache-bust corner thumbs after a change
  React.useEffect(() => { setStyle(home.style || ""); }, [home.style]);
  React.useEffect(() => { setSurroundings(home.surroundings || ""); }, [home.surroundings]);
  React.useEffect(() => { setStamp(Date.now()); }, [home.corners]);

  const pick = (key) => (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onUpload?.(key, f); };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-1 flex items-center gap-1.5"><Home className="h-3.5 w-3.5" /> Her home</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Her home is one coherent space. A shot whose brief names a room (e.g. "in her kitchen") is automatically set there.</p>

        <label className="text-[11px] text-zinc-400">House style <span className="text-zinc-600">— materials & aesthetic of the whole home</span></label>
        <textarea
          value={style} onChange={(e) => setStyle(e.target.value)} onBlur={() => onSaveHome?.({ style })} rows={2}
          placeholder="e.g. modern Indian flat, marble & tile floors, warm wood, neutral palette, plants, soft natural light"
          className="mt-1 w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none resize-none"
        />

        <label className="mt-3 block text-[11px] text-zinc-400">Balcony / window view <span className="text-zinc-600">— only applied to rooms that open outward</span></label>
        <textarea
          value={surroundings} onChange={(e) => setSurroundings(e.target.value)} onBlur={() => onSaveHome?.({ surroundings })} rows={2}
          placeholder="e.g. 12th-floor north-facing view of other buildings, HSR street, an overbridge barely visible"
          className="mt-1 w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none resize-none"
        />
        <p className="mt-1.5 text-[10px] text-zinc-600">Put the outside view HERE, not in House style — otherwise the city leaks into interior rooms (the bathroom shouldn't show a skyline). The view is used only for the balcony, terrace & living room. Saved on blur.</p>
      </section>

      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
        {(home.corners || []).map((c) => {
          const stage = busy[c.key];
          return (
            <div key={c.key} className="rounded-xl ring-1 ring-line-subtle bg-surface overflow-hidden">
              <div className="relative aspect-[4/3] bg-zinc-900 flex items-center justify-center">
                {stage ? (
                  <div className="flex flex-col items-center gap-1.5 text-center px-2">
                    <LoaderCircle className="h-5 w-5 animate-spin text-sky-400" />
                    <span className="text-[10px] text-sky-300">{stage}</span>
                  </div>
                ) : c.has_image ? (
                  <img src={`/api/home/${c.key}/thumb?t=${stamp}&character=${apiCharacter() || ""}`} alt={c.label} className="h-full w-full object-cover" />
                ) : (
                  <span className="text-[10px] text-zinc-600">no image yet</span>
                )}
                {c.view && <span className="absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 py-0.5 text-[11px] text-sky-300 ring-1 ring-sky-500/30">view</span>}
                {c.has_image && !stage && (
                  <button onClick={() => onDelete?.(c.key)} title="clear this corner"
                    className="absolute right-1.5 top-1.5 rounded bg-black/60 p-1 text-rose-300 hover:bg-black/85">
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
              <div className="px-2.5 py-2">
                <div className="text-[11px] font-medium text-zinc-200 truncate mb-1.5">{c.label}</div>
                <div className="flex gap-1.5">
                  <label className="flex-1 cursor-pointer rounded-md ring-1 ring-line py-1 text-[10px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-1">
                    <Upload className="h-3 w-3" /> Upload
                    <input type="file" accept="image/*" hidden onChange={pick(c.key)} disabled={!!stage} />
                  </label>
                  <button onClick={() => onGenerate?.(c.key)} disabled={!!stage}
                    className="flex-1 rounded-md ring-1 ring-line py-1 text-[10px] text-zinc-300 hover:bg-white/5 disabled:opacity-40 flex items-center justify-center gap-1">
                    <Sparkles className="h-3 w-3" /> Generate
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------- Overview ---------------- */

function Overview({ bio, gallery, parts, hasIdentity, refs, onSetBio, onDeleteRef, onToGallery, onImport, onUploadRef }) {
  // group parts by section for read-only display
  const grouped = {};
  for (const p of parts) {
    (grouped[p.section] = grouped[p.section] || []).push(p);
  }
  const entries = gallery.entries || [];

  return (
    <div className="space-y-6">
      {/* Identity reference — summary on the left, face management fills the space on the right */}
      <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-4">Identity reference</h3>
        <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
          {/* left: identity summary */}
          <div>
            <div className="flex gap-4">
              <div className="relative h-40 w-32 rounded-xl overflow-hidden ring-1 ring-line flex-shrink-0 bg-zinc-900 flex items-center justify-center">
                {bio.reference ? (
                  <>
                    <img src={refUrl(bio.reference)} alt="identity" className="h-full w-full object-cover" />
                    <div className="absolute top-1.5 left-1.5 rounded bg-black/60 backdrop-blur px-1.5 py-0.5 text-[11px] font-bold text-amber-300 ring-1 ring-amber-500/30">BIO</div>
                  </>
                ) : (
                  <span className="text-[10px] text-zinc-600 px-2 text-center">no identity ref</span>
                )}
              </div>
              <div className="text-[12px] space-y-2 min-w-0">
                <Row label="Identity lock" value={<span className="inline-flex items-center gap-1"><Lock className="h-3 w-3" />{hasIdentity ? "locked" : "unlocked"}</span>} accent={hasIdentity ? "emerald" : "amber"} />
                <Row label="Gate threshold" value={gallery.threshold ?? "—"} mono />
                <Row label="Gallery angles" value={entries.length} />
              </div>
            </div>
            <div className="mt-5">
              <div className="text-[11px] text-zinc-500 mb-2">Gallery angles</div>
              <div className="flex flex-wrap gap-1.5">
                {entries.length ? (
                  entries.map((a) => (
                    <span key={a} className="inline-flex items-center gap-1.5 rounded-full bg-white/5 ring-1 ring-line px-2.5 py-1 text-[10px] text-zinc-300">{a}</span>
                  ))
                ) : (
                  <span className="text-[11px] text-zinc-600">no gallery angles yet</span>
                )}
              </div>
            </div>
          </div>

          {/* right: identity reference management (import / upload / refs grid) */}
          <div className="lg:border-l lg:border-white/5 lg:pl-6">
            <FaceManager
              bio={bio} refs={refs}
              onSetBio={onSetBio} onDeleteRef={onDeleteRef} onToGallery={onToGallery}
              onImport={onImport} onUploadRef={onUploadRef}
            />
          </div>
        </div>
      </section>

      {/* Body-part text */}
      <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-4">Body-part text</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
          {Object.keys(grouped).length ? (
            Object.entries(grouped).map(([section, ps]) => (
              <PartGroup key={section} title={section} parts={ps} />
            ))
          ) : (
            <p className="text-[12px] text-zinc-600">no parts</p>
          )}
        </div>
      </section>
    </div>
  );
}

function PartGroup({ title, parts }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[11px] font-medium text-zinc-400">{title}</span>
      </div>
      <div className="space-y-1.5 pl-1">
        {parts.map((p) => (
          <div key={p.id} className="text-[12px] flex gap-2">
            <span className="text-zinc-600 w-24 flex-shrink-0">{p.label}</span>
            <span className={cn("text-zinc-300", !p.enabled && "opacity-40 line-through")}>{p.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value, mono, accent }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-zinc-500">{label}</span>
      <span
        className={cn(
          mono && "font-mono tabular-nums",
          accent === "emerald" && "text-emerald-300",
          accent === "amber" && "text-amber-300",
          !accent && "text-zinc-200"
        )}
      >
        {value}
      </span>
    </div>
  );
}

/* ---------------- Identity reference management (in overview) ---------------- */

function FaceManager({ bio, refs, onSetBio, onDeleteRef, onToGallery, onImport, onUploadRef }) {
  const [path, setPath] = useState("");

  const handleImport = () => {
    const p = path.trim();
    if (!p) return;
    onImport?.(p);
    setPath("");
  };

  const handleUpload = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) onUploadRef?.(f);
  };

  const handleToGallery = async (name) => {
    const view = await promptText({
      title: "Add to the identity gallery",
      body: "Which view is this? The gallery compares like with like — "
          + "scoring a profile against a frontal measures head angle, not identity.",
      placeholder: "front / side / three_quarter",
      defaultValue: "front", confirmLabel: "Add",
    });
    if (view) onToGallery?.(name, view);
  };

  return (
    <div className="space-y-5">
      {/* Import by path */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex-1 min-w-[240px] flex gap-2">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="C:\path\to\face.png"
            className="flex-1 rounded-lg bg-surface ring-1 ring-line px-3 py-2 text-[12px] text-zinc-200 focus:ring-white/30 outline-none"
          />
          <button
            onClick={handleImport}
            className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-2"
          >
            <Upload className="h-3.5 w-3.5" /> Import by path
          </button>
        </div>
        <label className="rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5 flex items-center justify-center gap-2 cursor-pointer">
          <Upload className="h-3.5 w-3.5" /> Upload face image
          <input type="file" accept="image/*" hidden onChange={handleUpload} />
        </label>
      </div>

      {/* Refs grid */}
      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(120px,1fr))]">
        {refs.map((r) => {
          const isBio = r.name === bio.reference;
          return (
            <div key={r.name} className={cn("rounded-xl ring-1 ring-line-subtle bg-surface overflow-hidden", isBio && "ring-amber-500/40")}>
              <div className="relative aspect-square overflow-hidden bg-zinc-900">
                <img src={refUrl(r.name, "thumb")} alt={r.name} className={cn("h-full w-full object-cover", !r.usable && "opacity-40")} />
                {isBio && (
                  <span className="absolute top-2 left-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] font-bold text-amber-300 ring-1 ring-amber-500/30">
                    BIO
                  </span>
                )}
                {!r.usable && (
                  <>
                    <span className="absolute inset-0 flex items-center justify-center">
                      <ImageOff className="h-5 w-5 text-rose-400" />
                    </span>
                    <span className="absolute top-2 right-2 rounded bg-rose-950/70 px-1.5 py-0.5 text-[11px] text-rose-300 ring-1 ring-rose-500/30">
                      no face
                    </span>
                  </>
                )}
              </div>
              <div className="px-2.5 py-2">
                <p className="truncate font-mono text-[10px] text-zinc-400 mb-1">{r.name}</p>
                <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1.5">
                  <span>{r.pose_class || "—"}</span>
                  <span className="tabular-nums">
                    {r.yaw > 0 ? "+" : ""}
                    {r.yaw ?? 0}° · {r.face_px ?? "—"}px
                  </span>
                </div>
                <div className="flex gap-1">
                  <button
                    disabled={!r.usable || isBio}
                    onClick={() => onSetBio?.(r.name)}
                    className="flex-1 rounded bg-white/5 hover:bg-white/10 py-1 text-[11px] text-zinc-300 disabled:opacity-30 flex items-center justify-center gap-0.5"
                  >
                    <Star className="h-2.5 w-2.5" /> {isBio ? "is BIO" : "set BIO"}
                  </button>
                  <button
                    onClick={() => handleToGallery(r.name)}
                    className="flex-1 rounded bg-white/5 hover:bg-white/10 py-1 text-[11px] text-zinc-300 flex items-center justify-center gap-0.5"
                  >
                    → gal
                  </button>
                  <button
                    onClick={() => onDeleteRef?.(r.name)}
                    className="rounded bg-white/5 hover:bg-rose-500/20 py-1 px-1.5 text-[11px] text-zinc-400 hover:text-rose-300"
                  >
                    <Trash2 className="h-2.5 w-2.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
        {!refs.length && <p className="text-[12px] text-zinc-500 col-span-full">No identity references yet. Import or upload one.</p>}
      </div>
    </div>
  );
}

/* ---------------- Advanced · Body ---------------- */

function AdvancedBody({ bodies, bodyPreview, bodyBusy, onUploadShape, onCreateBody, onSaveBody, onDiscardBody, onSelectBody, onDeleteBody }) {
  const [shapeRef, setShapeRef] = useState(null);
  const [figure, setFigure] = useState("");

  const list = bodies.bodies || [];

  const uploadShape = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !onUploadShape) return;
    try {
      const info = await onUploadShape(f);
      if (info?.name) setShapeRef(info.name);
    } catch {
      /* handled upstream */
    }
  };

  const handleSaveBody = async () => {
    const name = await promptText({ title: "Save as a body type",
      placeholder: "e.g. Original 48", confirmLabel: "Save" });
    if (name) onSaveBody?.(name);
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-6">
      {/* Left: body-type library + optional shape ref */}
      <div className="space-y-6">
        <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
          <h3 className="text-[12px] font-semibold text-zinc-300 mb-3">Body-type library</h3>
          <div className="space-y-1.5">
            {list.length ? (
              list.map((b) => (
                <div key={b.id} className={cn("flex items-center gap-2 rounded-lg px-3 py-2 ring-1 ring-line-subtle bg-surface", b.active && "ring-emerald-500/40")}>
                  <button onClick={() => onSelectBody?.(b.id)} title={b.build} className="flex items-center gap-2 flex-1 min-w-0 text-left">
                    <span className={cn("h-2 w-2 rounded-full flex-shrink-0", b.active ? "bg-emerald-400" : "bg-zinc-600")} />
                    <span className="text-[12px] text-zinc-300 truncate">{b.id}</span>
                  </button>
                  {b.active && <span className="text-[11px] text-emerald-300">active</span>}
                  <button onClick={() => onDeleteBody?.(b.id)} className="text-zinc-600 hover:text-rose-400"><Trash2 className="h-3 w-3" /></button>
                </div>
              ))
            ) : (
              <p className="text-[11px] text-zinc-600">No saved body types yet. Generate one and save it with a name.</p>
            )}
          </div>
        </section>

        <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
          <h3 className="text-[12px] font-semibold text-zinc-300 mb-1">Body-shape reference</h3>
          <p className="text-[10px] text-zinc-600 mb-3">Optional — a figure whose proportions to match (headless/faceless is fine).</p>
          {shapeRef ? (
            <div className="relative inline-block">
              <img src={refUrl(shapeRef)} alt="shape ref" className="h-28 w-24 rounded-md ring-1 ring-sky-500/40 object-cover" />
              <button onClick={() => setShapeRef(null)} title="remove shape reference" className="absolute -right-2 -top-2 rounded-full bg-zinc-800 p-0.5 text-rose-400 ring-1 ring-line"><X className="h-3 w-3" /></button>
            </div>
          ) : (
            <label className="rounded-lg border border-dashed border-white/15 p-5 flex flex-col items-center text-center hover:border-white/30 cursor-pointer">
              <ImagePlus className="h-4 w-4 text-zinc-500 mb-1.5" />
              <span className="text-[11px] text-zinc-500">Upload shape ref</span>
              <input type="file" accept="image/*" hidden onChange={uploadShape} />
            </label>
          )}
        </section>
      </div>

      {/* Right: generator (controls) + preview, side by side on wide screens */}
      <section className="rounded-2xl ring-1 ring-line-subtle bg-surface p-5">
        <h3 className="text-[12px] font-semibold text-zinc-300 mb-4">Generate body reference</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* controls */}
          <div className="flex flex-col">
            <label className="text-[11px] text-zinc-500 mb-1.5">Figure text</label>
            <textarea
              rows={6}
              value={figure}
              onChange={(e) => setFigure(e.target.value)}
              placeholder="e.g. dramatically curvy voluptuous hourglass — full bust, cinched waist, wide hips; blank = use her bio build"
              className="w-full flex-1 rounded-lg bg-surface ring-1 ring-line px-3 py-2 text-[13px] text-zinc-200 focus:ring-white/30 outline-none resize-none"
            />
            <button
              onClick={() => onCreateBody?.(shapeRef || null, figure.trim() || null)}
              disabled={!!bodyBusy}
              className="mt-3 rounded-lg bg-white text-black hover:bg-zinc-200 px-4 py-2.5 text-[12px] font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {bodyBusy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {bodyBusy ? "generating…" : `Generate body reference${shapeRef ? " (+ shape ref)" : ""}`}
            </button>
          </div>

          {/* preview */}
          <div className="flex flex-col">
            <label className="text-[11px] text-zinc-500 mb-1.5">Preview</label>
            <div className="flex-1 rounded-lg ring-1 ring-line-subtle bg-surface overflow-hidden flex items-center justify-center min-h-[280px]">
              {bodyBusy ? (
                <div className="flex flex-col items-center gap-2 text-center px-4">
                  <LoaderCircle className="h-6 w-6 animate-spin text-sky-400" />
                  <span className="text-[12px] text-sky-300">{bodyBusy} · ~1–2 min</span>
                </div>
              ) : bodyPreview ? (
                <img src={`/api/images/${bodyPreview.file}`} alt="body preview" className="h-full w-full object-contain" />
              ) : (
                <span className="text-[11px] text-zinc-600">preview appears here</span>
              )}
            </div>
            {bodyPreview && !bodyBusy && (
              <div className="mt-3 flex gap-2">
                <button onClick={handleSaveBody} className="flex-1 rounded-lg bg-white/10 hover:bg-white/15 px-4 py-2 text-[12px] text-zinc-200">Save as body type</button>
                <button onClick={() => onDiscardBody?.()} className="flex-1 rounded-lg ring-1 ring-line px-4 py-2 text-[12px] text-zinc-300 hover:bg-white/5">Discard</button>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

/* ---------------- Advanced · Parts ---------------- */

function AdvancedParts({ parts, onSavePart, onResetParts }) {
  const sections = [...new Set(parts.map((p) => p.section))];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[12px] font-semibold text-zinc-300">Body / identity parts</h3>
        <button onClick={() => onResetParts?.()} className="text-[11px] text-rose-400 hover:text-rose-300 flex items-center gap-1">
          <RefreshCw className="h-3 w-3" /> Reset to defaults
        </button>
      </div>

      <div className="space-y-7">
        {sections.map((sec) => (
          <div key={sec}>
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2.5">{sec}</div>
            <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(320px,1fr))]">
              {parts
                .filter((p) => p.section === sec)
                .map((p) => (
                  <div key={p.id} className={cn("rounded-xl ring-1 ring-line-subtle bg-surface p-4", !p.enabled && "opacity-50")}>
                    <div className="flex items-center gap-2.5 mb-2">
                      <button
                        type="button"
                        onClick={() => onSavePart?.(p.id, { enabled: !p.enabled })}
                        className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors", p.enabled ? "bg-emerald-500/80" : "bg-white/10")}
                      >
                        <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", p.enabled ? "translate-x-4" : "translate-x-0")} />
                      </button>
                      <span className="text-[12px] font-medium text-zinc-200 truncate">{p.label}</span>
                      {p.identity && <span className="rounded bg-amber-500/15 text-amber-300 px-1.5 py-0.5 text-[11px] font-semibold shrink-0">identity</span>}
                      {p.critical && <span className="rounded bg-sky-500/15 text-sky-300 px-1.5 py-0.5 text-[11px] font-semibold shrink-0">load-bearing</span>}
                      <code className="ml-auto font-mono text-[10px] text-zinc-600 truncate">{p.id}</code>
                    </div>
                    <input
                      defaultValue={p.text}
                      onBlur={(e) => onSavePart?.(p.id, { text: e.target.value })}
                      disabled={!p.enabled}
                      className="w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2 text-[12px] text-zinc-200 focus:ring-white/30 outline-none disabled:opacity-40"
                    />
                    {p.note && <p className="mt-2 text-[11px] text-zinc-500 leading-snug">{p.note}</p>}
                  </div>
                ))}
            </div>
          </div>
        ))}
        {!parts.length && <p className="text-[12px] text-zinc-500">No parts.</p>}
      </div>
    </div>
  );
}
