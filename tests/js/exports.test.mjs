// Unit tests for static/js/lib/exports.js: the addresses and the period of the export links.
// [EXP-1] [EXP-2] [EXP-3]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  FORMATS, defaultPeriod, periodProblem, projectsExportUrl, timeExportUrl,
} from "../../momato/static/js/lib/exports.js";

test("[EXP-3] two formats are offered", () => {
  assert.deepEqual(FORMATS.map((f) => f.key), ["csv", "xlsx"]);
});

test("[EXP-1] the project export carries the filters of the screen", () => {
  const route = { view: "projects", node: 7, status: "progress", q: "sensor", name: "", coordinator: "Rivera" };
  assert.equal(
    projectsExportUrl(route, "csv"),
    "api/exports/projects?format=csv&node=7&status=progress&q=sensor&coordinator=Rivera",
  );
  assert.equal(projectsExportUrl({ node: null, status: null, q: "", name: "", coordinator: "" }, "xlsx"),
    "api/exports/projects?format=xlsx");
  // what is typed is encoded
  assert.equal(projectsExportUrl({ q: "a&b c" }, "csv"), "api/exports/projects?format=csv&q=a%26b+c");
});

test("[EXP-2] the time export carries the period and branch", () => {
  assert.equal(
    timeExportUrl({ start: "2026-09-28", end: "2026-10-02", node: 3 }, "xlsx"),
    "api/exports/time-entries?format=xlsx&start=2026-09-28&end=2026-10-02&node=3",
  );
  assert.equal(
    timeExportUrl({ start: "2026-09-28", end: "2026-10-02", node: null }, "csv"),
    "api/exports/time-entries?format=csv&start=2026-09-28&end=2026-10-02",
  );
});

test("[EXP-2] the period offered is what the screen shows, else the last 30 days", () => {
  const buckets = [
    { start: "2026-09-28", end: "2026-09-28" },
    { start: "2026-10-02", end: "2026-10-02" },
  ];
  assert.deepEqual(defaultPeriod(buckets, "2026-10-08"), { start: "2026-09-28", end: "2026-10-02" });
  assert.deepEqual(defaultPeriod([], "2026-10-08"), { start: "2026-09-08", end: "2026-10-08" });
  assert.deepEqual(defaultPeriod(undefined, "2026-03-05"), { start: "2026-02-03", end: "2026-03-05" });
});

test("[EXP-2] a period is checked like the server checks it", () => {
  assert.equal(periodProblem("2026-09-28", "2026-10-02"), "");
  assert.equal(periodProblem("2026-09-28", "2026-09-28"), "");
  assert.equal(periodProblem("", "2026-10-02"), "Choose both days.");
  assert.equal(periodProblem("2026-10-02", "not a date"), "Choose both days.");
  assert.equal(periodProblem("2026-13-45", "2026-14-45"), "Choose both days.");
  assert.equal(periodProblem("2026-10-02", "2026-09-28"), "The period ends before it starts.");
  assert.equal(periodProblem("2020-01-01", "2026-10-02"), "A period of at most three years can be exported.");
  assert.equal(periodProblem("2023-10-02", "2026-10-02"), "");
});
