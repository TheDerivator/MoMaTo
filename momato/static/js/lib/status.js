// Status chips of the Projects list (PL-2): fixed order, zero counts hidden, one selected.

/**
 * The chips to show: every status of the bootstrap in its order with its count; chips with a
 * count of 0 are hidden, except the selected one (so it can always be cleared).
 */
export function chips(statuses, counts, selected) {
  return statuses
    .map((s) => ({
      key: s.key,
      label: s.label,
      hue: s.hue,
      gray: s.gray,
      hidden: s.hidden,
      count: counts[s.key] ?? 0,
      selected: s.key === selected,
    }))
    .filter((c) => c.count > 0 || c.selected);
}

/** Clicking selects one status, clicking it again clears it. */
export function nextSelection(current, clicked) {
  return current === clicked ? null : clicked;
}

export function statusByKey(statuses) {
  return new Map(statuses.map((s) => [s.key, s]));
}
