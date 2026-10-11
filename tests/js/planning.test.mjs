// Unit tests for static/js/lib/planning.js: wording and units of the People planning table.
// [PPL-3] [PPL-4] [PPL-5] [PPL-6]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  LEGENDS, MODES, PERIODS, cellView, gridTemplate, hiddenNote, lineTotal, numberText, toneClass,
  totalView,
} from "../../momato/static/js/lib/planning.js";

test("the modes and periods are the design's", () => {
  assert.deepEqual(MODES.map((m) => m.label), ["Planned", "Spent", "Compare"]);
  assert.deepEqual(PERIODS.map((p) => p.label), ["Past week", "Past month", "Past year"]);
  assert.ok(LEGENDS.planned.some((l) => l.label === "Over capacity"));
  assert.ok(LEGENDS.compare.some((l) => l.label === "On track"));
});

test("numbers have one decimal for days and two for hours, half up, no trailing zeros", () => {
  assert.equal(numberText(12), "12");
  assert.equal(numberText(12.5), "12.5");
  assert.equal(numberText(12.25), "12.3");
  assert.equal(numberText(12.04), "12");
  assert.equal(numberText(7.25, "hours"), "7.25");
  assert.equal(numberText(7.254, "hours"), "7.25");
  assert.equal(numberText(0.005, "hours"), "0.01");
  assert.equal(numberText(-3.5), "-3.5");
  assert.equal(numberText(0), "0");
});

test("class names for the stylesheet", () => {
  assert.equal(toneClass("nearly_full"), "pp-nearly-full");
  assert.equal(toneClass("on_track"), "pp-on-track");
  assert.equal(toneClass("over"), "pp-over");
});

test("[PPL-3] a planned cell", () => {
  const cell = { value: 23, reference: 61.5, cls: "light" };
  assert.deepEqual(cellView(cell, "planned", "days"), {
    label: "23", sub: "", cls: "light", title: "23 d planned of 61.5 d available",
  });
  assert.deepEqual(cellView({ value: 0, reference: 50, cls: "empty" }, "planned", "days"), {
    label: "–", sub: "", cls: "empty", title: "",
  });
});

test("[PPL-3] a planned total reads free or over", () => {
  assert.deepEqual(totalView({ value: 120, reference: 245, free: 125, cls: "light" }, "planned", "days"), {
    label: "120 d", sub: "125 d free", tone: "good",
  });
  assert.deepEqual(totalView({ value: 250.5, reference: 245, free: -5.5, cls: "over" }, "planned", "days"), {
    label: "250.5 d", sub: "5.5 d over", tone: "bad",
  });
});

test("[PPL-4] a spent cell in hours and in days", () => {
  const hours = cellView({ value: 7.5, reference: 8, cls: "nearly_full" }, "spent", "hours");
  assert.equal(hours.label, "7.5");
  assert.equal(hours.title, "7.5 h spent of 8 h available");
  const days = cellView({ value: 3.25, reference: 4, cls: "nearly_full" }, "spent", "days");
  assert.equal(days.label, "3.3");
  assert.equal(days.cls, "nearly_full");
  assert.deepEqual(totalView({ value: 30, reference: 40, cls: "nearly_full" }, "spent", "hours"), {
    label: "30 h", sub: "of 40 h", tone: "",
  });
});

test("[PPL-5] a compare cell: spent large, planned small, unplanned says so", () => {
  assert.deepEqual(cellView({ value: 5, reference: 6, cls: "on_track" }, "compare", "days"), {
    label: "5", sub: "of 6", cls: "on_track", title: "5 d spent · 6 d planned",
  });
  const unplanned = cellView({ value: 2, reference: 0, cls: "unplanned" }, "compare", "days");
  assert.equal(unplanned.sub, "unplanned");
  assert.equal(cellView({ value: 0, reference: 0, cls: "empty" }, "compare", "days").sub, "");
});

test("[PPL-5] a compare total says how much of the plan was spent", () => {
  assert.deepEqual(totalView({ value: 12, reference: 14, percent: 86, cls: "on_track" }, "compare", "days"), {
    label: "12 d", sub: "86% of plan", tone: "good",
  });
  assert.equal(totalView({ value: 30, reference: 10, percent: 300, cls: "over" }, "compare", "days").tone, "bad");
});

test("lines of a drill-down", () => {
  const compare = { kind: "project", total: { value: 4.5, reference: 6 } };
  assert.equal(lineTotal(compare, "compare", "days"), "4.5 / 6 d");
  assert.equal(lineTotal({ kind: "other_work", total: { value: 8 } }, "compare", "hours"), "8 h");
  assert.equal(lineTotal({ kind: "project", total: { value: 3 } }, "spent", "days"), "3 d");
});

test("[PPL-6] the note about hidden hours", () => {
  assert.equal(hiddenNote(0), "");
  assert.equal(hiddenNote(1), "1 person in this branch whose hours you can't see.");
  assert.equal(hiddenNote(59), "59 people in this branch whose hours you can't see.");
});

test("the grid has the person, the total and a column per bucket", () => {
  assert.equal(gridTemplate(8), "minmax(230px, 1.5fr) 120px repeat(8, minmax(62px, 1fr))");
});
