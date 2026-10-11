// Keyset paging of the project list (PL-7): merging pages, and resetting on a filter change.

/** A fresh list for a set of filters. `key` names the filters the pages belong to. */
export function emptyList(key = "") {
  return { key, items: [], total: 0, nextAfter: null, loaded: false };
}

/** The first page of the filters `key`; it replaces whatever was shown. */
export function firstPage(list, key, page) {
  if (list.key !== key) return list; // an answer for filters that have been left already
  return { key, items: [...page.items], total: page.total, nextAfter: page.next_after, loaded: true };
}

/**
 * A later page: rows are appended, never repeated (a project already shown is skipped), and an
 * answer for other filters than the current ones is ignored.
 */
export function nextPage(list, key, page) {
  if (list.key !== key) return list;
  const seen = new Set(list.items.map((p) => p.number));
  const added = page.items.filter((p) => !seen.has(p.number));
  return {
    key,
    items: [...list.items, ...added],
    total: page.total,
    nextAfter: page.next_after,
    loaded: true,
  };
}

/** Changing the filters starts over: the list is emptied under the new key. */
export function reset(list, key) {
  return list.key === key ? list : emptyList(key);
}

/** The key of a set of filters, the same for the same filters. */
export function filterKey(filters) {
  return JSON.stringify([
    filters.node ?? null,
    filters.status ?? null,
    filters.q ?? "",
    filters.name ?? "",
    filters.coordinator ?? "",
  ]);
}
