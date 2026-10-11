// Unit tests for static/js/lib/routes.js: parsing locations and building links. [SH-8] [SH-4]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  HEADS, buildUrl, filtersOf, listRouteOf, menuItem, parseRoute, relativePath, usesTree,
} from "../../momato/static/js/lib/routes.js";

test("the root redirects to the projects", () => {
  assert.deepEqual(parseRoute(""), { view: "redirect", to: "projects" });
});

test("a list route carries its filters and the selected node", () => {
  const route = parseRoute("projects", "?node=3&status=progress&q=pump&name=ab&coordinator=to");
  assert.deepEqual(route, {
    view: "projects",
    node: 3,
    status: "progress",
    q: "pump",
    name: "ab",
    coordinator: "to",
  });
  assert.deepEqual(parseRoute("projects"), {
    view: "projects", node: null, status: null, q: "", name: "", coordinator: "",
  });
});

test("a project route has its number and tab", () => {
  assert.deepEqual(parseRoute("projects/4102").tab, "overview");
  assert.equal(parseRoute("projects/4102/planning").tab, "planning");
  assert.equal(parseRoute("projects/4102/people").number, 4102);
  assert.equal(parseRoute("projects/4102/nonsense").tab, "overview");
  assert.equal(parseRoute("projects/4102/remarks").view, "project");
});

test("the other screens", () => {
  assert.deepEqual(parseRoute("timesheet"), { view: "timesheet", week: null });
  assert.deepEqual(parseRoute("timesheet/2026-W41"), { view: "timesheet", week: "2026-W41" });
  const people = parseRoute("people", "?node=2&mode=compare&period=month&person=7");
  assert.deepEqual(people, { view: "people", node: 2, mode: "compare", period: "month", person: 7 });
  assert.equal(parseRoute("people").mode, "planned");
  const plans = parseRoute("plans/3", "?node=2&project=4102");
  assert.deepEqual(plans, { view: "plans", plan: 3, node: 2, project: 4102 });
  assert.equal(parseRoute("profile").view, "profile");
  assert.deepEqual(parseRoute("admin/people"), { view: "admin", section: "people", id: null });
  assert.deepEqual(parseRoute("admin/people/12"), { view: "admin", section: "people", id: 12 });
  assert.equal(parseRoute("admin/people/x").id, null);
  assert.equal(parseRoute("no/such").view, "notfound");
});

test("links are built relative to the base and drop empty filters", () => {
  assert.equal(buildUrl({ view: "projects", node: null, status: null, q: "", name: "", coordinator: "" }), "projects");
  assert.equal(
    buildUrl({ view: "projects", node: 3, status: "progress", q: "pump station", name: "", coordinator: "" }),
    "projects?node=3&status=progress&q=pump+station",
  );
  assert.equal(buildUrl({ view: "project", number: 4102, tab: "overview" }), "projects/4102");
  assert.equal(buildUrl({ view: "project", number: 4102, tab: "logbook" }), "projects/4102/logbook");
  assert.equal(buildUrl({ view: "timesheet", week: null }), "timesheet");
  assert.equal(buildUrl({ view: "timesheet", week: "2026-W40" }), "timesheet/2026-W40");
  assert.equal(buildUrl({ view: "people", node: 2, mode: "spent", period: "month", person: null }),
    "people?node=2&mode=spent&period=month");
  assert.equal(buildUrl({ view: "people", node: null, mode: "planned", period: "year", person: 7 }),
    "people?person=7");
  assert.equal(buildUrl({ view: "plans", plan: 3, node: null, project: 4102 }), "plans/3?project=4102");
  assert.equal(buildUrl({ view: "admin", section: null }), "admin");
  assert.equal(buildUrl({ view: "admin", section: "org", id: null }), "admin/org");
  assert.equal(buildUrl({ view: "admin", section: "people", id: 12 }), "admin/people/12");
  assert.equal(buildUrl({ view: "unknown" }), "projects");
});

test("a built link parses back to the same filters", () => {
  const route = { view: "projects", node: 12, status: "stopped", q: "ä & b", name: "x", coordinator: "y" };
  assert.deepEqual(parseRoute("projects", `?${buildUrl(route).split("?")[1]}`), route);
});

test("paths are taken relative to the base path", () => {
  assert.equal(relativePath("/projects/4102", "/"), "projects/4102");
  assert.equal(relativePath("/momato/projects/4102", "/momato/"), "projects/4102");
  assert.equal(relativePath("/momato/", "/momato/"), "");
  assert.equal(relativePath("/momato/projects/", "/momato"), "projects");
});

test("a project page belongs to Projects in the menu, and the tree applies to three views", () => {
  assert.equal(menuItem({ view: "project" }), "projects");
  assert.equal(menuItem({ view: "plans" }), "plans");
  assert.equal(usesTree({ view: "projects" }), true);
  assert.equal(usesTree({ view: "people" }), true);
  assert.equal(usesTree({ view: "plans" }), true);
  assert.equal(usesTree({ view: "project" }), false);
  assert.equal(usesTree({ view: "timesheet" }), false);
});

test("every head the router knows is listed for the server", () => {
  for (const head of ["projects", "timesheet", "people", "plans", "profile", "admin"]) {
    assert.ok(HEADS.includes(head), head);
  }
});

test("a project page keeps the filters of the list it came from [PP-1]", () => {
  const route = parseRoute("projects/4102/logbook", "?node=3&status=progress&q=pump");
  assert.deepEqual(route, {
    view: "project", number: 4102, tab: "logbook",
    node: 3, status: "progress", q: "pump", name: "", coordinator: "",
  });
  assert.equal(buildUrl(route), "projects/4102/logbook?node=3&status=progress&q=pump");
  assert.deepEqual(listRouteOf(route), {
    view: "projects", node: 3, status: "progress", q: "pump", name: "", coordinator: "",
  });
  assert.equal(buildUrl(listRouteOf(route)), "projects?node=3&status=progress&q=pump");
  assert.deepEqual(filtersOf(route), {
    node: 3, status: "progress", q: "pump", name: "", coordinator: "",
  });
  assert.equal(
    buildUrl({ view: "project", number: 4102, tab: "people", ...filtersOf(route) }),
    "projects/4102/people?node=3&status=progress&q=pump",
  );
  assert.equal(buildUrl({ view: "project", number: 4102, tab: "overview" }), "projects/4102");
  assert.deepEqual(listRouteOf({ view: "project", number: 1 }), {
    view: "projects", node: null, status: null, q: "", name: "", coordinator: "",
  });
});
