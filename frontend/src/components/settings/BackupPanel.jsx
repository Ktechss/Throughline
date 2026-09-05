import React, { useEffect, useState } from "react";
import { api, saveAs, mb, STAGE } from "@/api/throughline";
import { toast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";
import { Modal, Button } from "@/components/ui/modal";
import {
  Archive, Check, Download, Loader2, RotateCcw, Upload, AlertTriangle, HardDrive,
} from "lucide-react";

// BACKUP / RESTORE.
//
// `data/` is gitignored and runs 1-11 GB, so a clone gives you a working app and
// an empty studio. Recovering a character used to mean reading a tar listing by
// hand, stopping the backend so sqlite's WAL was not torn mid-copy, extracting,
// and checking that bio.json's pointers still resolved. This is that, as a
// button.
//
// The restore flow is INSPECT-THEN-CHOOSE on purpose. An archive can carry a
// character you already have, and "replace" is the only irreversible thing here,
// so nothing is written until the manifest has been read and shown.

// Rendered inside the character chip's own <button>, so this is a span: nesting
// a button in a button is invalid markup and React warns about it.
const TileCheck = ({ checked, onClick, disabled }) => (
  <span
    role={onClick ? "checkbox" : undefined}
    aria-checked={onClick ? !!checked : undefined}
    onClick={onClick}
    className={cn(
      "h-4 w-4 shrink-0 grid place-items-center rounded ring-1 transition-colors",
      disabled
        ? "bg-white/10 text-white/40 ring-line"
        : checked
        ? "bg-emerald-500 text-black ring-emerald-400"
        : "bg-black/40 text-transparent ring-white/25 hover:ring-white/50",
    )}
    title={disabled ? "always included" : undefined}
  >
    <Check className="h-3 w-3" strokeWidth={3} />
  </span>
);

export default function BackupPanel() {
  const [opts, setOpts] = useState(null);
  const [chars, setChars] = useState([]);
  const [parts, setParts] = useState(["identity"]);
  const [dest, setDest] = useState("");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [archives, setArchives] = useState([]);
  const [restorePath, setRestorePath] = useState("");
  const [inspecting, setInspecting] = useState(null);
  const [reloadHint, setReloadHint] = useState(false);

  const loadOpts = (cids) =>
    api
      .get(`/api/backup/options?characters=${(cids || []).join(",")}`)
      .then((d) => {
        setOpts(d);
        if (!cids) setChars(d.characters.map((c) => c.id));
      })
      .catch((e) => setErr(String(e)));

  const loadArchives = () =>
    api.get("/api/backup/archives").then((d) => setArchives(d.archives || []))
       .catch((e) => setErr(String(e)));

  useEffect(() => { loadOpts(); loadArchives(); }, []);
  useEffect(() => { if (chars.length) loadOpts(chars); }, [chars.join(",")]);

  const toggleChar = (id) =>
    setChars((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  const togglePart = (key) => {
    if (opts?.parts.find((p) => p.key === key)?.required) return;
    setParts((p) => (p.includes(key) ? p.filter((x) => x !== key) : [...p, key]));
  };

  const total = (opts?.sizes && parts.reduce((n, k) => n + (opts.sizes[k] || 0), 0)) || 0;

  // The established await-loop: poll /api/jobs/{id} and show its stage.
  const runJob = async (jid, label) => {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const st = await api.get(`/api/jobs/${jid}`);
      setBusy(`${label}: ${STAGE[st.stage] || st.stage}${st.step ? ` · ${st.step}` : ""}`);
      if (st.done) {
        if (st.error) throw new Error(st.error);
        return st.run;
      }
    }
  };

  const create = async () => {
    setErr(null); setBusy("starting…");
    try {
      const { job } = await api.send("/api/backup", "POST", {
        characters: chars, parts, dest: dest.trim() || null,
      });
      const r = await runJob(job, "Backing up");
      await loadArchives();
      setBusy(null);
      toast.ok(`Backed up ${r.files} files · ${mb(r.bytes)}`, r.path);
    } catch (e) { setErr(String(e)); setBusy(null); }
  };

  const inspect = async (path) => {
    setErr(null); setBusy("reading archive…");
    try {
      const m = await api.send("/api/backup/inspect", "POST", { path });
      setInspecting(m);
      setBusy(null);
    } catch (e) { setErr(String(e)); setBusy(null); }
  };

  const upload = async (file) => {
    setErr(null); setBusy(`uploading ${file.name}…`);
    try {
      const r = await api.putRaw(
        `/api/backup/upload/${encodeURIComponent(file.name)}`, file);
      setBusy(null);
      await inspect(r.path);
    } catch (e) { setErr(String(e)); setBusy(null); }
  };

  const doRestore = async (decisions) => {
    setInspecting(null); setErr(null); setBusy("starting…");
    try {
      const { job } = await api.send("/api/backup/restore", "POST", {
        path: inspecting.path, decisions,
      });
      const r = await runJob(job, "Restoring");
      setBusy(null);
      // A restore is the one result worth keeping on screen: it says what was
      // overwritten AND what was deliberately left alone, which is the whole
      // point of restoring only the parts an archive carries.
      for (const x of r.restored) {
        toast.ok(
          `Restored ${x.restored_as} · ${x.files} files, ${x.runs} runs`,
          `replaced ${x.restored.join(", ")}` +
            (x.kept.length ? ` · kept ${x.kept.join(", ")}` : "") +
            (x.snapshot ? " · snapshot saved" : ""));
      }
      setReloadHint(true);
    } catch (e) { setErr(String(e)); setBusy(null); }
  };

  return (
    <section className="mt-8">
      <h2 className="text-[13px] font-semibold text-zinc-300">Backup &amp; restore</h2>
      <p className="text-[11px] text-zinc-500 mt-0.5 mb-3">
        <code className="text-zinc-400">data/</code> is not in git, so a fresh clone
        gives you a working app and an empty studio. This is the other half.
      </p>

      {err && (
        <div className="mb-3 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 px-3 py-2 text-[12px] text-rose-300">
          {err}
        </div>
      )}

      {reloadHint && (
        <div className="mb-3 flex items-center justify-between gap-3 rounded-xl bg-emerald-500/10 ring-1 ring-emerald-500/30 px-3 py-2">
          <span className="text-[12px] text-emerald-200">
            Restored. The studio is still showing what it loaded before.
          </span>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      )}

      {/* ---------------------------------------------------------- create */}
      <div className="rounded-xl bg-surface ring-1 ring-line p-3.5 space-y-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
            Who
          </div>
          <div className="flex flex-wrap gap-2">
            {(opts?.characters || []).map((c) => (
              <button key={c.id} onClick={() => toggleChar(c.id)}
                className={cn("flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px] ring-1 transition-colors",
                  chars.includes(c.id)
                    ? "bg-white/[0.06] ring-white/20 text-zinc-100"
                    : "bg-white/[0.01] ring-line text-zinc-500")}>
                <TileCheck checked={chars.includes(c.id)} />
                {c.name}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
            What
          </div>
          <div className="space-y-1.5">
            {(opts?.parts || []).map((p) => (
              <div key={p.key}
                className="flex items-start gap-2.5 rounded-lg bg-surface px-2.5 py-2">
                <div className="pt-0.5">
                  <TileCheck checked={parts.includes(p.key) || p.required}
                    disabled={p.required} onClick={() => togglePart(p.key)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-zinc-200">{p.label}</span>
                    <span className="text-[11px] text-zinc-500">
                      {mb(opts?.sizes?.[p.key])}
                    </span>
                    {p.required && (
                      <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        always
                      </span>
                    )}
                    {p.couples_rows && (
                      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
                        files + rows together
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">{p.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
            Where
          </div>
          <input value={dest} onChange={(e) => setDest(e.target.value)}
            placeholder={opts?.dir || "data/backups"}
            className="w-full rounded-lg bg-black/40 ring-1 ring-line px-2.5 py-1.5 text-[12px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:ring-white/25" />
          <p className="text-[11px] text-zinc-500 mt-1">
            A folder on this machine — an external drive is the point. Leave blank
            for <code className="text-zinc-400">{opts?.dir || "data/backups"}</code>.
            {opts && <> · {mb(opts.free)} free</>}
          </p>
        </div>

        <div className="flex items-center gap-3 pt-0.5">
          <button onClick={create} disabled={!!busy || !chars.length}
            className="inline-flex items-center gap-2 rounded-lg bg-white text-black px-3 py-1.5 text-[12px] font-medium disabled:opacity-40">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Archive className="h-3.5 w-3.5" />}
            Back up {chars.length > 1 ? `${chars.length} characters` : "her"}
          </button>
          <span className="text-[11px] text-zinc-500">
            {busy || `${mb(total)} · uncompressed, because webp and jpg do not shrink`}
          </span>
        </div>
      </div>

      {/* --------------------------------------------------------- restore */}
      <div className="mt-3 rounded-xl bg-surface ring-1 ring-line p-3.5">
        <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
          Restore
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={restorePath} onChange={(e) => setRestorePath(e.target.value)}
            placeholder="/path/to/kiara.tar"
            className="flex-1 min-w-[220px] rounded-lg bg-black/40 ring-1 ring-line px-2.5 py-1.5 text-[12px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:ring-white/25" />
          <button onClick={() => inspect(restorePath.trim())}
            disabled={!restorePath.trim() || !!busy}
            className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-1.5 text-[12px] text-zinc-100 disabled:opacity-40">
            <RotateCcw className="h-3.5 w-3.5" /> Inspect
          </button>
          <label className="inline-flex items-center gap-2 rounded-lg bg-white/[0.04] ring-1 ring-line px-3 py-1.5 text-[12px] text-zinc-300 cursor-pointer hover:ring-white/25">
            <Upload className="h-3.5 w-3.5" /> Upload
            <input type="file" accept=".tar" hidden
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload(f); }} />
          </label>
        </div>
        <p className="text-[11px] text-zinc-500 mt-1.5">
          A path is read straight off this machine — nothing is copied first, which
          is what makes an 11 GB archive practical. Upload is for one that lives
          somewhere else. Nothing is written until you have seen what is inside.
        </p>
      </div>

      {/* -------------------------------------------------------- archives */}
      {archives.length > 0 && (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">
            On this machine
          </div>
          <div className="space-y-1.5">
            {archives.map((a) => (
              <div key={a.path}
                className="flex items-center gap-3 rounded-lg bg-surface ring-1 ring-white/5 px-2.5 py-2">
                <HardDrive className="h-3.5 w-3.5 text-zinc-600 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-zinc-200 truncate">{a.name}</span>
                    {a.snapshot && (
                      <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        auto-snapshot
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">
                    {mb(a.bytes)} · {a.created?.replace("T", " ")} ·{" "}
                    {(a.characters || []).map((c) => `${c.name} (${c.runs} runs)`).join(", ")
                      || a.error}
                  </div>
                </div>
                <button onClick={() => inspect(a.path)} disabled={!!busy}
                  className="text-[11px] text-zinc-400 hover:text-zinc-100 disabled:opacity-40">
                  Restore
                </button>
                <button
                  onClick={() => saveAs(`/api/backup/archives/${encodeURIComponent(a.name)}/file`, a.name)}
                  title="Download to your browser"
                  className="text-zinc-500 hover:text-zinc-200">
                  <Download className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {inspecting && (
        <RestoreModal manifest={inspecting} onClose={() => setInspecting(null)}
          onConfirm={doRestore} />
      )}
    </section>
  );
}

// Step 2 of inspect-then-choose. Everything the manual recovery had to derive
// with tar and sqlite3 is already on screen before anything is written.
function RestoreModal({ manifest, onClose, onConfirm }) {
  const [modes, setModes] = useState(() =>
    Object.fromEntries(manifest.characters.map((c) => [c.id, c.conflict ? "new" : "replace"])));

  const decisions = manifest.characters.map((c) => ({
    archive_id: c.id, mode: c.conflict ? modes[c.id] : "new", name: c.name,
  }));

  return (
    <Modal
      open
      onClose={onClose}
      title="Restore"
      subtitle={manifest.path}
      size="md"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={() => onConfirm(decisions)}>Restore</Button>
        </>
      }
    >
      <div className="space-y-3">
          <div className="text-[11px] text-zinc-500">
            {mb(manifest.archive_bytes)} · {manifest.files} files ·{" "}
            {(manifest.parts || []).join(", ")}
            {manifest.legacy && " · made by hand (no manifest) — read from the archive itself"}
          </div>

          {manifest.characters.map((c) => (
            <div key={c.id} className="rounded-xl bg-surface ring-1 ring-line p-3">
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-zinc-100">{c.name || c.id}</span>
                <span className="text-[11px] text-zinc-500">{c.id}</span>
              </div>
              <div className="text-[11px] text-zinc-500 mt-1">
                {c.files} files · {mb(c.bytes)} · {c.runs} runs · {c.wardrobe} outfits
                {c.gallery_entries != null && ` · ${c.gallery_entries} gallery`}
                {c.threshold != null && ` · threshold ${c.threshold}`}
              </div>

              {c.conflict ? (
                <>
                  <div className="mt-2 flex items-start gap-2 rounded-lg bg-amber-500/10 ring-1 ring-amber-500/25 px-2.5 py-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-300 shrink-0 mt-0.5" />
                    <div className="text-[11px] text-amber-200">
                      <span className="font-medium">{c.id}</span> already exists here.
                    </div>
                  </div>
                  <div className="mt-2 space-y-1.5">
                    {[
                      ["replace", `Replace ${c.id}`,
                       "A full snapshot is taken first. Only what this archive carries is overwritten — anything it does not hold is left alone."],
                      ["new", "Restore side by side",
                       "Lands under a new id and leaves her untouched. Run ids are re-minted, because they are unique across the whole database."],
                    ].map(([val, label, why]) => (
                      <button key={val} onClick={() => setModes((m) => ({ ...m, [c.id]: val }))}
                        className={cn("w-full text-left rounded-lg px-2.5 py-2 ring-1 transition-colors",
                          modes[c.id] === val
                            ? "bg-white/[0.06] ring-white/25"
                            : "bg-white/[0.01] ring-line hover:ring-white/20")}>
                        <div className="flex items-center gap-2">
                          <TileCheck checked={modes[c.id] === val} />
                          <span className="text-[12px] text-zinc-100">{label}</span>
                        </div>
                        <div className="text-[11px] text-zinc-500 mt-1 pl-6">{why}</div>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-[11px] text-emerald-300/80 mt-1.5">
                  New here — nothing to overwrite.
                </div>
              )}
            </div>
          ))}
      </div>
    </Modal>
  );
}
