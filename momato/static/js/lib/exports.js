// Export links (EXP-1 – EXP-3): the address of a file for the filters and period on screen.
// The server answers GET with the file, so a plain link downloads it with the session cookie.

export const FORMATS = [
  { key: "csv", label: "CSV (.csv)" },
  { key: "xlsx", label: "Excel (.xlsx)" },
];

function query(entries) {
  const params = new URLSearchParams();
  for (const [key, value] of entries) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.toString();
}

/** The project list as it is filtered on screen (a route of the Projects view). */
export function projectsExportUrl(route, format) {
  const text = query([
    ["format", format],
    ["node", route.node],
    ["status", route.status],
    ["q", route.q],
    ["name", route.name],
    ["coordinator", route.coordinator],
  ]);
  return `api/exports/projects?${text}`;
}

/** Booked time of a period, for a branch (null: everyone the caller may see). */
export function timeExportUrl({ start, end, node }, format) {
  return `api/exports/time-entries?${query([["format", format], ["start", start], ["end", end], ["node", node]])}`;
}

/** The period offered for a time export: what the screen shows, else the last 30 days. */
export function defaultPeriod(buckets, today) {
  if (buckets?.length) return { start: buckets[0].start, end: buckets[buckets.length - 1].end };
  const end = new Date(`${today}T00:00:00Z`);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 30);
  return { start: start.toISOString().slice(0, 10), end: today };
}

/** Whether a period is something the server accepts: both days, in order, at most three years. */
export function periodProblem(start, end) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return "Choose both days.";
  const days = (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000;
  if (Number.isNaN(days)) return "Choose both days.";
  if (days < 0) return "The period ends before it starts.";
  if (days > 366 * 3) return "A period of at most three years can be exported.";
  return "";
}
