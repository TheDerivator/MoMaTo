// Unit tests for static/js/lib/tree.js: branches, rows and the breadcrumb. [SH-3] [SH-5]
import assert from "node:assert/strict";
import { test } from "node:test";

import { breadcrumb, buildTree, nodeLabel, pathTo, subtreeIds, treeRows } from "../../momato/static/js/lib/tree.js";

const org = [
  { id: 1, parent_id: null, name: "Brightwater", position: 0, is_department: false },
  { id: 3, parent_id: 1, name: "R&D", position: 1, is_department: true },
  { id: 2, parent_id: 1, name: "STL", position: 0, is_department: true },
  { id: 4, parent_id: 2, name: "Quality", position: 0, is_department: false },
  { id: 5, parent_id: 4, name: "Lab", position: 0, is_department: false },
  { id: 6, parent_id: 2, name: "Process", position: 1, is_department: false },
];
const tree = buildTree(org);

test("children are ordered by position and know their depth", () => {
  assert.equal(tree.root.name, "Brightwater");
  assert.deepEqual(tree.root.children.map((c) => c.name), ["STL", "R&D"]);
  assert.equal(tree.nodes.get(5).depth, 3);
  assert.equal(tree.nodes.get(2).depth, 1);
});

test("a subtree has the node and everything below it", () => {
  assert.deepEqual(subtreeIds(tree, 2).sort(), [2, 4, 5, 6]);
  assert.deepEqual(subtreeIds(tree, 5), [5]);
  assert.deepEqual(subtreeIds(tree, 99), []);
});

test("the path runs from the root to the node", () => {
  assert.deepEqual(pathTo(tree, 5).map((n) => n.name), ["Brightwater", "STL", "Quality", "Lab"]);
  assert.deepEqual(pathTo(tree, 99), []);
});

test("rows show expanded branches with their counts", () => {
  const counts = { 1: 20, 2: 12, 3: 8, 4: 7, 5: 3, 6: 5 };
  const rows = treeRows(tree, new Set(), counts);
  assert.deepEqual(rows.map((r) => [r.name, r.depth, r.count]), [
    ["Brightwater", 0, 20],
    ["STL", 1, 12],
    ["Quality", 2, 7],
    ["Lab", 3, 3],
    ["Process", 2, 5],
    ["R&D", 1, 8],
  ]);
  assert.equal(rows[0].hasChildren, true);
  assert.equal(rows[3].hasChildren, false);
});

test("collapsing a node hides its descendants only", () => {
  const rows = treeRows(tree, new Set([2]), {});
  assert.deepEqual(rows.map((r) => r.name), ["Brightwater", "STL", "R&D"]);
  assert.equal(rows[1].expanded, false);
  assert.equal(rows[1].count, 0); // a node without a count shows 0
});

test("the breadcrumb has ancestors below the root, the node and its child menu", () => {
  const counts = { 4: 7, 6: 5, 5: 3 };
  const crumb = breadcrumb(tree, 4, counts);
  assert.deepEqual(crumb.ancestors, [{ id: 1, name: "Brightwater" }, { id: 2, name: "STL" }]);
  assert.deepEqual(crumb.current, { id: 4, name: "Quality" });
  assert.deepEqual(crumb.kids, [{ id: 5, name: "Lab", count: 3, hasChildren: false }]);
  const atRoot = breadcrumb(tree, 1, { 2: 12, 3: 8 });
  assert.deepEqual(atRoot.ancestors, []);
  assert.deepEqual(atRoot.kids.map((k) => [k.name, k.count, k.hasChildren]), [
    ["STL", 12, true],
    ["R&D", 8, false],
  ]);
});

test("an unknown node falls back to the root", () => {
  assert.equal(breadcrumb(tree, 99, {}).current.name, "Brightwater");
  assert.equal(nodeLabel(tree, 2), "STL");
  assert.equal(nodeLabel(tree, 99), "");
});
