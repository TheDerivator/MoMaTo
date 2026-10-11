// URLs of the app (SH-8): parsing a location into a route, and building links.
// Paths are relative to the page's <base href>, so the app works under a URL prefix.

/** The first path segments the browser router knows; the server serves each as the page. */
export const HEADS = ["projects", "timesheet", "people", "plans", "profile", "admin"];

/** The path below the base, without leading or trailing slashes ("" at the root). */
export function relativePath(pathname, basePath) {
  const base = basePath.endsWith("/") ? basePath : `${basePath}/`;
  const below = pathname.startsWith(base) ? pathname.slice(base.length) : pathname.replace(/^\//, "");
  return below.replace(/\/+$/, "");
}

const PROJECT_TABS = ["planning", "people", "remarks", "logbook", "details"];

/** `/projects?node=3&status=progress` and so on, as a route object. */
function listFilters(params) {
  return {
    node: params.has("node") ? Number(params.get("node")) : null,
    status: params.get("status") || null,
    q: params.get("q") || "",
    name: params.get("name") || "",
    coordinator: params.get("coordinator") || "",
  };
}

export function parseRoute(path, search = "") {
  const params = new URLSearchParams(search);
  const parts = path.split("/").filter(Boolean);
  const [head, second, third] = parts;
  if (!head) return { view: "redirect", to: "projects" };
  if (head === "projects") {
    if (second && /^\d+$/.test(second)) {
      // The list filters ride along, so "‹ ›" and "← Projects" know the list it came from (PP-1).
      const tab = PROJECT_TABS.includes(third) ? third : "overview";
      return { view: "project", number: Number(second), tab, ...listFilters(params) };
    }
    return { view: "projects", ...listFilters(params) };
  }
  if (head === "timesheet") return { view: "timesheet", week: second || null };
  if (head === "people") {
    return {
      view: "people",
      node: params.has("node") ? Number(params.get("node")) : null,
      mode: params.get("mode") || "planned",
      period: params.get("period") || "week",
      person: params.get("person") ? Number(params.get("person")) : null,
    };
  }
  if (head === "plans") {
    return {
      view: "plans",
      plan: second ? Number(second) : null,
      node: params.has("node") ? Number(params.get("node")) : null,
      project: params.get("project") ? Number(params.get("project")) : null,
    };
  }
  if (head === "profile") return { view: "profile" };
  if (head === "admin") {
    return { view: "admin", section: second || null, id: third && /^\d+$/.test(third) ? Number(third) : null };
  }
  return { view: "notfound" };
}

function withParams(path, entries) {
  const params = new URLSearchParams();
  for (const [key, value] of entries) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

function listEntries(route) {
  return [
    ["node", route.node],
    ["status", route.status],
    ["q", route.q],
    ["name", route.name],
    ["coordinator", route.coordinator],
  ];
}

/** The list filters of a route (a list or a project page), without the view. */
export function filtersOf(route) {
  return {
    node: route.node ?? null,
    status: route.status ?? null,
    q: route.q ?? "",
    name: route.name ?? "",
    coordinator: route.coordinator ?? "",
  };
}

/** The list a project page came from: the same filters, as a list route. */
export function listRouteOf(route) {
  return { view: "projects", ...filtersOf(route) };
}

/** The link (relative to the base) of a route object. */
export function buildUrl(route) {
  switch (route.view) {
    case "projects":
      return withParams("projects", listEntries(route));
    case "project":
      return withParams(
        route.tab && route.tab !== "overview"
          ? `projects/${route.number}/${route.tab}`
          : `projects/${route.number}`,
        listEntries(route),
      );
    case "timesheet":
      return route.week ? `timesheet/${route.week}` : "timesheet";
    case "people":
      return withParams("people", [
        ["node", route.node],
        ["mode", route.mode === "planned" ? null : route.mode],
        ["period", route.mode && route.mode !== "planned" && route.period !== "week" ? route.period : null],
        ["person", route.person],
      ]);
    case "plans":
      return withParams(route.plan ? `plans/${route.plan}` : "plans", [
        ["node", route.node],
        ["project", route.project],
      ]);
    case "profile":
      return "profile";
    case "admin":
      if (!route.section) return "admin";
      return route.id ? `admin/${route.section}/${route.id}` : `admin/${route.section}`;
    default:
      return "projects";
  }
}

/** Which main-menu item a route belongs to (a project page belongs to Projects). */
export function menuItem(route) {
  if (route.view === "project") return "projects";
  return route.view;
}

/** Whether the organisation tree applies to the view (SH-3). */
export function usesTree(route) {
  return route.view === "projects" || route.view === "people" || route.view === "plans";
}
