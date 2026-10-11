// Unit tests for static/js/lib/logbook.js: filter chips and the sentence of an entry. [LB-2] [LB-3]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  FILTERS, VALUE_LIMIT, clip, dayOf, hasPair, sentence, timeOf,
} from "../../momato/static/js/lib/logbook.js";

test("the chips are the design's, Everything first", () => {
  assert.deepEqual(
    FILTERS.map((f) => f.label),
    ["Everything", "Title", "Status", "Dates", "People", "Action plans"],
  );
  assert.deepEqual(
    FILTERS.map((f) => f.key),
    ["all", "title", "status", "dates", "people", "plans"],
  );
});

test("an entry reads 'Name changed field', and 'You' for the viewer", () => {
  const entry = { actor: { id: 4, name: "Anna Claes" }, field: "end_date", field_label: "End date" };
  assert.deepEqual(sentence(entry, 9), { who: "Anna Claes", verb: "changed", what: "end date" });
  assert.deepEqual(sentence(entry, 4), { who: "You", verb: "changed", what: "end date" });
  const created = { actor: { id: 4, name: "Anna Claes" }, field: "created", field_label: "Project" };
  assert.deepEqual(sentence(created, 9), { who: "Anna Claes", verb: "created", what: "the project" });
});

test("long values are cut and can be expanded", () => {
  assert.deepEqual(clip("short"), { text: "short", clipped: false });
  const long = "x".repeat(VALUE_LIMIT + 20);
  const cut = clip(long);
  assert.equal(cut.clipped, true);
  assert.equal(cut.text, `${"x".repeat(VALUE_LIMIT)}…`);
  assert.deepEqual(clip("x".repeat(VALUE_LIMIT)), { text: "x".repeat(VALUE_LIMIT), clipped: false });
  assert.equal(clip("abc def ghi", 8).text, "abc def…");
});

test("only entries with an old value show a pair", () => {
  assert.equal(hasPair({ from_value: "Idea", to_value: "In progress" }), true);
  assert.equal(hasPair({ from_value: null, to_value: "Added Anna" }), false);
  assert.equal(hasPair({ to_value: "Created" }), false);
});

test("the local day and time of a date-time", () => {
  const moment = new Date(2026, 9, 8, 14, 5); // local
  const iso = moment.toISOString();
  assert.equal(dayOf(iso), "2026-10-08");
  assert.equal(timeOf(iso), "14:05");
  assert.equal(timeOf(new Date(2026, 0, 2, 3, 4).toISOString()), "03:04");
});
