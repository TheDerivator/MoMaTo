// Unit tests for static/js/lib/format.js against the shared table of tests/fixtures/formatting.json.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  formatDate,
  formatDays,
  formatHours,
  formatLongDate,
  formatMonth,
  formatShortDate,
  hoursNumber,
  initials,
  parseIso,
  plural,
  relativeDate,
  toIso,
} from "../../momato/static/js/lib/format.js";

const table = JSON.parse(readFileSync(new URL("../fixtures/formatting.json", import.meta.url)));

test("[R4.10] dates", () => {
  for (const [iso, text] of table.date) assert.equal(formatDate(iso), text);
});

test("[R4.10] short dates", () => {
  for (const [iso, text] of table.short_date) assert.equal(formatShortDate(iso), text);
});

test("[R4.10] months", () => {
  for (const [iso, text] of table.month) assert.equal(formatMonth(iso), text);
});

test("[R4.10] long dates", () => {
  for (const [iso, text] of table.long_date) assert.equal(formatLongDate(iso), text);
});

test("[R4.10] relative dates", () => {
  for (const c of table.relative) assert.equal(relativeDate(c.date, c.today), c.text);
});

test("[R4.10] days have at most one decimal, halves up, exactly", () => {
  for (const [value, text] of table.days) assert.equal(formatDays(value), text, `days ${value}`);
});

test("[R4.10] hours are whole or have up to two decimals", () => {
  for (const [minutes, text] of table.hours) assert.equal(formatHours(minutes), text, `${minutes}`);
});

test("floating point days round like their decimal text", () => {
  assert.equal(formatDays(12.45), "12.5 d");
  assert.equal(formatDays(0.05), "0.1 d");
  assert.equal(formatDays(0.25), "0.3 d");
  assert.equal(formatDays(2), "2 d");
  assert.equal(formatDays(-2.5), "-2.5 d");
});

test("ISO dates round-trip without time zone shifts", () => {
  for (const iso of ["2026-01-01", "2026-03-29", "2026-10-25", "2024-02-29", "2026-12-31"]) {
    assert.equal(toIso(parseIso(iso)), iso);
  }
});

test("initials", () => {
  assert.equal(initials("Anna Claes"), "AC");
  assert.equal(initials("Hannes Van den Berg"), "HV");
  assert.equal(initials("chloe.martens"), "CM");
  assert.equal(initials("admin"), "AD");
  assert.equal(initials("Tomás Rivera"), "TR");
});

test("plural", () => {
  assert.equal(plural(1, "project", "projects"), "1 project");
  assert.equal(plural(214, "project", "projects"), "214 projects");
  assert.equal(plural(0, "project", "projects"), "0 projects");
});

test("[R4.10] hours without the unit", () => {
  assert.equal(hoursNumber(480), "8");
  assert.equal(hoursNumber(90), "1.5");
  assert.equal(hoursNumber(0), "0");
});
