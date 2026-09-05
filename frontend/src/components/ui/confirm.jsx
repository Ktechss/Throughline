import React, { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Modal, Button } from "@/components/ui/modal";

// A confirm dialog you can `await` from anywhere, including code that is not in
// the React tree.
//
// That last part is the whole reason this is imperative rather than a component.
// Fourteen of the app's confirmations live inside useStudio.js — a hook full of
// async actions, with no JSX and nowhere to hang a <ConfirmDialog open={…}>.
// Rewriting each of them into open/pending/resolve state would have been a large
// diff across a 643-line file for no behaviour change, so the call site keeps its
// shape and only the implementation moves:
//
//     if (!window.confirm("Delete 12 outfits?")) return;
//     if (!(await confirm({ title: "Delete 12 outfits?", danger: true }))) return;
//
// Same module-level-store pattern as use-toast.jsx, for the same reason.

let _emit = null;

/**
 * @returns {Promise<boolean>} true if the user confirmed.
 */
export function confirm(opts) {
  const options = typeof opts === "string" ? { title: opts } : (opts || {});
  // No host mounted (a test, or a render that has not happened yet) — fall back
  // to the browser rather than hanging forever on a promise nobody can resolve.
  if (!_emit) return Promise.resolve(window.confirm(options.title || "Are you sure?"));
  return new Promise((resolve) => _emit({ ...options, resolve }));
}

/**
 * The same dialog with a text field. Replaces window.prompt.
 * @returns {Promise<string|null>} the trimmed value, or null if cancelled.
 */
export function promptText(opts) {
  const options = typeof opts === "string" ? { title: opts } : (opts || {});
  if (!_emit) {
    const v = window.prompt(options.title || "");
    return Promise.resolve(v == null ? null : v.trim() || null);
  }
  return new Promise((resolve) => _emit({ ...options, input: true, resolve }));
}

export function ConfirmHost() {
  const [req, setReq] = useState(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    _emit = (r) => { setValue(r.defaultValue || ""); setReq(r); };
    return () => { _emit = null; };
  }, []);

  if (!req) return null;

  // An input dialog resolves to the string (or null); a plain one to a boolean.
  const done = (ok) => {
    req.resolve(req.input ? (ok ? value.trim() || null : null) : ok);
    setReq(null);
  };

  return (
    <Modal
      open
      onClose={() => done(false)}
      title={req.title}
      size="sm"
      footer={
        <>
          <Button onClick={() => done(false)}>{req.cancelLabel || "Cancel"}</Button>
          <Button
            variant={req.danger ? "danger" : "primary"}
            onClick={() => done(true)}
            disabled={req.input && !value.trim()}
            autoFocus={!req.input}
          >
            {req.confirmLabel || (req.danger ? "Delete" : "Confirm")}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3">
        {req.danger && (
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
        )}
        <div className="min-w-0 flex-1">
          {(req.body || !req.input) && (
            <div className="text-[12px] text-zinc-400 leading-relaxed">
              {req.body || "This cannot be undone."}
            </div>
          )}
          {req.input && (
            <input
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) done(true); }}
              placeholder={req.placeholder || ""}
              className="mt-2 w-full rounded-lg bg-black/40 ring-1 ring-line px-2.5 py-1.5 text-[12px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:ring-white/30"
            />
          )}
        </div>
      </div>
    </Modal>
  );
}

export default confirm;
