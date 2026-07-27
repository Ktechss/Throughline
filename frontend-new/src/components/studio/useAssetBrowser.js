import { useState, useMemo, useEffect } from "react";

/**
 * Shared browse/filter/paginate logic for large asset lists (outfits, poses).
 * Handles N categories and 50+ items per category without rendering everything at once.
 *
 * @param {Object} opts
 * @param {Array} opts.items        Flat list of asset items (each must have a `category` field).
 * @param {Array<string>} opts.categories  Category ids (first is the default selection).
 * @param {number} opts.pageSize    How many items to render per "load more" batch.
 */
export function useAssetBrowser({ items, categories, pageSize = 12 }) {
  const [category, setCategory] = useState(categories[0] ?? "All");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(pageSize);

  // Reset pagination whenever the filter changes so we never over-render stale rows.
  useEffect(() => {
    setVisibleCount(pageSize);
  }, [category, query, pageSize]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      const catOk = category === "All" || it.category === category;
      const haystack = `${it.name || it.label || ""} ${it.text || ""}`.toLowerCase();
      return catOk && (!q || haystack.includes(q));
    });
  }, [items, category, query]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  const loadMore = () => setVisibleCount((c) => c + pageSize);

  return {
    category,
    setCategory,
    query,
    setQuery,
    filtered,
    visible,
    hasMore,
    loadMore,
    total: filtered.length,
    visibleCount,
  };
}