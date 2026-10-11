// Unit tests for static/js/lib/paging.js and lib/status.js. [PL-2] [PL-7]
import assert from "node:assert/strict";
import { test } from "node:test";

import { emptyList, filterKey, firstPage, nextPage, reset } from "../../momato/static/js/lib/paging.js";
import { chips, nextSelection, statusByKey } from "../../momato/static/js/lib/status.js";

const page = (numbers, nextAfter, total = 7) => ({
  items: numbers.map((number) => ({ number })),
  total,
  next_after: nextAfter,
});

test("a first page fills the list under its key", () => {
  const list = firstPage(emptyList("a"), "a", page([9, 8, 7], 7));
  assert.deepEqual(list.items.map((p) => p.number), [9, 8, 7]);
  assert.equal(list.nextAfter, 7);
  assert.equal(list.total, 7);
  assert.equal(list.loaded, true);
});

test("pages merge without duplicates, in order", () => {
  let list = firstPage(emptyList("a"), "a", page([9, 8, 7], 7));
  list = nextPage(list, "a", page([7, 6, 5], 5)); // 7 repeats: a project shifted
  assert.deepEqual(list.items.map((p) => p.number), [9, 8, 7, 6, 5]);
  list = nextPage(list, "a", page([4, 3], null));
  assert.deepEqual(list.items.map((p) => p.number), [9, 8, 7, 6, 5, 4, 3]);
  assert.equal(list.nextAfter, null);
});

test("an answer for other filters is ignored", () => {
  const list = firstPage(emptyList("b"), "b", page([5, 4], null, 2));
  const late = nextPage(list, "a", page([3, 2], null));
  assert.equal(late, list);
  assert.equal(firstPage(list, "a", page([1], null)), list);
});

test("changing the filters starts over", () => {
  const filled = firstPage(emptyList("a"), "a", page([9, 8], 8));
  assert.equal(reset(filled, "a"), filled);
  const fresh = reset(filled, "b");
  assert.deepEqual(fresh, emptyList("b"));
  assert.equal(fresh.loaded, false);
});

test("the filter key is the same for the same filters", () => {
  const a = filterKey({ node: 3, status: null, q: "x", name: "", coordinator: "" });
  assert.equal(a, filterKey({ node: 3, q: "x" }));
  assert.notEqual(a, filterKey({ node: 4, q: "x" }));
  assert.notEqual(a, filterKey({ node: 3, q: "x", status: "idea" }));
});

const statuses = [
  { key: "idea", label: "Idea", hue: 90, gray: false, hidden: false },
  { key: "rejected", label: "Rejected idea", hue: 285, gray: true, hidden: false },
  { key: "stopped", label: "Stopped", hue: 20, gray: false, hidden: true },
];

test("chips keep the order and hide empty statuses, but a selected one stays", () => {
  const shown = chips(statuses, { idea: 3, stopped: 2 }, null);
  assert.deepEqual(shown.map((c) => [c.key, c.count]), [["idea", 3], ["stopped", 2]]);
  assert.equal(shown[1].hidden, true); // the chip of a hidden status stays visible
  const withSelected = chips(statuses, { idea: 3 }, "rejected");
  assert.deepEqual(withSelected.map((c) => c.key), ["idea", "rejected"]);
  assert.equal(withSelected[1].selected, true);
});

test("clicking a chip selects it and clicking again clears it", () => {
  assert.equal(nextSelection(null, "idea"), "idea");
  assert.equal(nextSelection("idea", "idea"), null);
  assert.equal(nextSelection("idea", "rejected"), "rejected");
  assert.equal(statusByKey(statuses).get("stopped").label, "Stopped");
});
