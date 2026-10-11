// Unit tests for static/js/lib/timeline.js: the window and bar geometry. [R4.12] [PL-4]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { barGeometry, daysBetween, position, timelineWindow } from "../../momato/static/js/lib/timeline.js";

const buckets = JSON.parse(readFileSync(new URL("../fixtures/buckets.json", import.meta.url)));

test("[R4.12] the window runs from 1 January of last year to 31 December of next year", () => {
  for (const c of buckets.windows) {
    assert.deepEqual(timelineWindow(c.today), { start: c.start, end: c.end });
  }
});

test("positions are percentages of the window, clamped", () => {
  const window = { start: "2025-01-01", end: "2027-12-31" };
  assert.equal(position("2025-01-01", window), 0);
  assert.equal(position("2027-12-31", window), 100);
  assert.equal(position("2024-06-01", window), 0);
  assert.equal(position("2030-01-01", window), 100);
  // 645 days into a window of 1,094 days (2025-01-01 to 2027-12-31).
  assert.ok(Math.abs(position("2026-10-08", window) - (645 / 1094) * 100) < 1e-9);
});

test("a bar starts where the project starts and is at least 1 % wide", () => {
  const window = { start: "2025-01-01", end: "2027-12-31" };
  const bar = barGeometry("2025-11-03", "2027-03-31", window);
  assert.ok(bar.left > 0 && bar.left < 100);
  assert.ok(bar.width > 40);
  const day = barGeometry("2026-05-05", "2026-05-05", window);
  assert.equal(day.width, 1);
  const before = barGeometry("2020-01-01", "2020-06-30", window);
  assert.deepEqual(before, { left: 0, width: 1 });
});

test("a bar partly outside the window is cut at its edge", () => {
  const window = { start: "2025-01-01", end: "2027-12-31" };
  const bar = barGeometry("2024-01-01", "2025-07-01", window);
  assert.equal(bar.left, 0);
  assert.ok(bar.width > 10 && bar.width < 30);
});

test("whole days between dates", () => {
  assert.equal(daysBetween("2026-10-01", "2026-10-08"), 7);
  assert.equal(daysBetween("2026-10-08", "2026-10-01"), -7);
  assert.equal(daysBetween("2026-03-28", "2026-03-30"), 2); // across a clock change
});
