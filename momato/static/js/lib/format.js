// Display formatting of dates, days and hours (R4.10): en-GB, locale-free, rounding half up.
// Mirrors momato/domain/formatting.py; both pass tests/fixtures/formatting.json.

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const RELATIVE_DAYS_LIMIT = 7;
const DAY_MS = 86_400_000;

/** `"2026-10-08"` as a UTC calendar date (no time zone surprises). */
export function parseIso(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function toIso(date) {
  return date.toISOString().slice(0, 10);
}

export function formatDate(iso) {
  const d = parseIso(iso);
  return `${d.getUTCDate()} ${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatShortDate(iso) {
  const d = parseIso(iso);
  return `${d.getUTCDate()} ${MONTHS_SHORT[d.getUTCMonth()]}`;
}

export function formatMonth(iso) {
  const d = parseIso(iso);
  return `${MONTHS_SHORT[d.getUTCMonth()]} ’${String(d.getUTCFullYear() % 100).padStart(2, "0")}`;
}

export function formatLongDate(iso) {
  const d = parseIso(iso);
  const weekday = WEEKDAYS_LONG[(d.getUTCDay() + 6) % 7];
  return `${weekday} ${d.getUTCDate()} ${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "Today", "Yesterday", "n days ago" below a week, else the date. */
export function relativeDate(iso, todayIso) {
  const age = Math.round((parseIso(todayIso) - parseIso(iso)) / DAY_MS);
  if (age <= 0) return "Today";
  if (age === 1) return "Yesterday";
  if (age < RELATIVE_DAYS_LIMIT) return `${age} days ago`;
  return formatDate(iso);
}

/** A number or an exact fraction string ("25/2") as [numerator, denominator]. */
function asFraction(value) {
  if (typeof value === "string" && value.includes("/")) {
    const [n, d] = value.split("/").map(Number);
    return [n, d];
  }
  return [Number(value), 1];
}

/** `value` times `scale`, rounded half up, exactly for fractions and with a guard for floats. */
function scaledRounded(value, scale) {
  const [n, d] = asFraction(value);
  if (d !== 1) return Math.floor((2 * n * scale + d) / (2 * d));
  return Math.floor(n * scale + 0.5 + 1e-9);
}

function decimal(value, places) {
  const scale = 10 ** places;
  const scaled = scaledRounded(value, scale);
  const whole = Math.trunc(Math.abs(scaled) / scale);
  const fraction = Math.abs(scaled) % scale;
  const sign = scaled < 0 ? "-" : "";
  if (fraction === 0) return `${sign}${whole}`;
  return `${sign}${whole}.${String(fraction).padStart(places, "0").replace(/0+$/, "")}`;
}

/** Days with at most one decimal: "12 d", "12.5 d". */
export function formatDays(days) {
  return `${decimal(days, 1)} d`;
}

/** Hours of a number of minutes: whole, else up to two decimals: "8 h", "1.5 h". */
export function formatHours(minutes) {
  const [n, d] = asFraction(minutes);
  const hours = [n, d * 60];
  const scaled = Math.floor((2 * hours[0] * 100 + hours[1]) / (2 * hours[1]));
  const whole = Math.trunc(Math.abs(scaled) / 100);
  const fraction = Math.abs(scaled) % 100;
  const sign = scaled < 0 ? "-" : "";
  const text = fraction === 0 ? `${whole}` : `${whole}.${String(fraction).padStart(2, "0").replace(/0+$/, "")}`;
  return `${sign}${text} h`;
}

/** Hours of a number of minutes without the unit: "8", "1.5". */
export function hoursNumber(minutes) {
  return formatHours(minutes).replace(/ h$/, "");
}

/** "Anna Claes" -> "AC"; at most two letters. */
export function initials(name) {
  const words = name.split(/[\s.]+/).filter(Boolean);
  const letters = words.map((w) => w[0].toUpperCase());
  if (letters.length === 1) return name.slice(0, 2).toUpperCase();
  return letters.slice(0, 2).join("");
}

export function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}
