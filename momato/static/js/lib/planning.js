// People planning presentation (PPL-1 – PPL-5): how a cell, a total and a line read, from the
// numbers and classes the server computed (R4.5). No rule lives here: only wording and units.

export const MODES = [
  { key: "planned", label: "Planned" },
  { key: "spent", label: "Spent" },
  { key: "compare", label: "Compare" },
];

export const PERIODS = [
  { key: "week", label: "Past week" },
  { key: "month", label: "Past month" },
  { key: "year", label: "Past year" },
];

export const UNIT_SHORT = { hours: "h", days: "d" };

/** The legend of each mode: the classes that colour its cells. */
export const LEGENDS = {
  planned: [
    { cls: "comfortable", label: "Comfortable" },
    { cls: "nearly_full", label: "Nearly full" },
    { cls: "over", label: "Over capacity" },
  ],
  spent: [
    { cls: "comfortable", label: "Comfortable" },
    { cls: "nearly_full", label: "Nearly full" },
    { cls: "over", label: "Over capacity" },
  ],
  compare: [
    { cls: "on_track", label: "On track" },
    { cls: "under", label: "Under plan" },
    { cls: "over", label: "Over plan or unplanned" },
  ],
};

/** A number as people read it: at most one decimal for days, two for hours, no trailing zeros. */
export function numberText(value, unit = "days") {
  const places = unit === "hours" ? 2 : 1;
  const scale = 10 ** places;
  const rounded = Math.floor(Math.abs(value) * scale + 0.5 + 1e-9) / scale;
  const text = String(rounded);
  return value < 0 && rounded !== 0 ? `-${text}` : text;
}

/** The classes of a mode's cells, as the stylesheet names them. */
export function toneClass(cls) {
  return `pp-${cls.replace(/_/g, "-")}`;
}

/** A cell of the table: its text, the small line under it, its class and its tooltip. */
export function cellView(cell, mode, unit) {
  const u = UNIT_SHORT[unit];
  const label = cell.value ? numberText(cell.value, unit) : "–";
  if (mode === "planned") {
    const title = cell.value
      ? `${numberText(cell.value, unit)} d planned of ${numberText(cell.reference ?? 0, unit)} d available`
      : "";
    return { label, sub: "", cls: cell.cls, title };
  }
  if (mode === "spent") {
    const title = `${numberText(cell.value, unit)} ${u} spent of ${numberText(cell.reference ?? 0, unit)} ${u} available`;
    return { label, sub: "", cls: cell.cls, title };
  }
  // compare: spent large, "of {planned}" small; unplanned work says so
  let sub = "";
  if (cell.reference) sub = `of ${numberText(cell.reference, unit)}`;
  else if (cell.cls === "unplanned") sub = "unplanned";
  const title = `${numberText(cell.value, unit)} ${u} spent · ${numberText(cell.reference ?? 0, unit)} ${u} planned`;
  return { label, sub, cls: cell.cls, title };
}

/** A row's total: the label, the line under it and whether that line is good or a warning. */
export function totalView(total, mode, unit) {
  const u = UNIT_SHORT[unit];
  if (mode === "planned") {
    const free = total.free ?? 0;
    return {
      label: `${numberText(total.value, unit)} d`,
      sub: free >= 0 ? `${numberText(free, unit)} d free` : `${numberText(-free, unit)} d over`,
      tone: free >= 0 ? "good" : "bad",
    };
  }
  if (mode === "compare") {
    return {
      label: `${numberText(total.value, unit)} ${u}`,
      sub: `${total.percent ?? 0}% of plan`,
      tone: total.cls === "on_track" ? "good" : total.cls === "empty" ? "" : "bad",
    };
  }
  return {
    label: `${numberText(total.value, unit)} ${u}`,
    sub: total.reference ? `of ${numberText(total.reference, unit)} ${u}` : "",
    tone: "",
  };
}

/** The line under a person's name in a drill-down for one project or other kind of line. */
export function lineTotal(line, mode, unit) {
  const u = UNIT_SHORT[unit];
  if (mode === "compare" && line.kind === "project") {
    return `${numberText(line.total.value, unit)} / ${numberText(line.total.reference ?? 0, unit)} ${u}`;
  }
  return `${numberText(line.total.value, unit)} ${u}`;
}

/** The note about people whose hours the viewer may not see (PPL-6); "" when there are none. */
export function hiddenNote(count) {
  if (!count) return "";
  return `${count} ${count === 1 ? "person" : "people"} in this branch whose hours you can't see.`;
}

/** The grid of the table: person, total and one column per bucket. */
export function gridTemplate(bucketCount) {
  return `minmax(230px, 1.5fr) 120px repeat(${bucketCount}, minmax(62px, 1fr))`;
}
