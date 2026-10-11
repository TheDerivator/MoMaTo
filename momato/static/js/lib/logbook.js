// The logbook's presentation (LB-2, LB-3): filter chips, the sentence of an entry, long values.

/** The filter chips, in order; "all" is Everything (the other fields appear only there). */
export const FILTERS = [
  { key: "all", label: "Everything" },
  { key: "title", label: "Title" },
  { key: "status", label: "Status" },
  { key: "dates", label: "Dates" },
  { key: "people", label: "People" },
  { key: "plans", label: "Action plans" },
];

/** Values longer than this are cut in the chip and shown in full on expand (LB-3). */
export const VALUE_LIMIT = 80;

/** Who did it ("You" for the viewer), what was done and to which field. */
export function sentence(entry, viewerId) {
  const who = entry.actor.id === viewerId ? "You" : entry.actor.name;
  if (entry.field === "created") return { who, verb: "created", what: "the project" };
  return { who, verb: "changed", what: entry.field_label.toLowerCase() };
}

/** A value for a chip: the text shown, and whether it was cut (then it can be expanded). */
export function clip(value, limit = VALUE_LIMIT) {
  if (value.length <= limit) return { text: value, clipped: false };
  return { text: `${value.slice(0, limit).trimEnd()}…`, clipped: true };
}

/** An entry has an "old → new" pair when it has an old value; otherwise just the new one. */
export function hasPair(entry) {
  return entry.from_value !== null && entry.from_value !== undefined;
}

const two = (n) => String(n).padStart(2, "0");

/** The local calendar date ("2026-10-08") of an ISO date-time such as "2026-10-08T12:05:00Z". */
export function dayOf(isoDateTime) {
  const moment = new Date(isoDateTime);
  return `${moment.getFullYear()}-${two(moment.getMonth() + 1)}-${two(moment.getDate())}`;
}

/** The local time of day ("14:05") of an ISO date-time. */
export function timeOf(isoDateTime) {
  const moment = new Date(isoDateTime);
  return `${two(moment.getHours())}:${two(moment.getMinutes())}`;
}
