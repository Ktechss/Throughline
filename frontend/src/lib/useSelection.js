import { useCallback, useMemo, useState } from "react";

// Reusable multi-select for any grid/list. Holds a Set of ids; nothing is
// selected until the user picks. selectAll toggles between all-of-`ids` and none.
export function useSelection() {
  const [sel, setSel] = useState(() => new Set());

  const toggle = useCallback((id) => {
    setSel((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }, []);

  const clear = useCallback(() => setSel(new Set()), []);

  const selectAll = useCallback((ids) => {
    setSel((s) => (s.size === ids.length ? new Set() : new Set(ids)));
  }, []);

  return useMemo(() => ({
    selected: sel,
    ids: [...sel],
    count: sel.size,
    has: (id) => sel.has(id),
    toggle, clear, selectAll,
  }), [sel, toggle, clear, selectAll]);
}
