// Action plans (AP-2 – AP-7): which plans a branch shows, rights to manage them, the words of the
// meta line and the timeline's geometry. The grouping itself is done by the server (the owner's
// department first); this module only presents it.
import { subtreeIds } from "./tree.js";
import { parseIso } from "./format.js";

/** The fixed palette a plan's colour is chosen from (AP-1): hues of the design. */
export const PLAN_HUES = [285, 155, 235, 60, 330, 20];

/** Plans owned inside the selected branch (AP-2), in the order the server listed them. */
export function plansInBranch(plans, tree, nodeId) {
  const inside = new Set(subtreeIds(tree, nodeId ?? tree.root.id));
  return plans.filter((plan) => inside.has(plan.owner_org_node_id));
}

/** The plan to show: the one in the URL when the branch has it, else the first. */
export function chosenPlan(visible, wantedId) {
  return visible.find((p) => p.id === wantedId) ?? visible[0] ?? null;
}

/** Whether a permission reach covers a node: everywhere, or inside one of its branches. */
export function reachCovers(reach, tree, nodeId) {
  if (reach.everywhere) return true;
  const path = [];
  let id = nodeId;
  while (id !== null && id !== undefined && tree.nodes.has(id)) {
    path.push(id);
    id = tree.nodes.get(id).parent_id;
  }
  return path.some((p) => reach.node_ids.includes(p));
}

/** Every node a reach covers, root first: the choices of an owner picker. */
export function reachableNodes(reach, tree) {
  const result = [];
  const walk = (node, inside) => {
    const ok = inside || reach.everywhere || reach.node_ids.includes(node.id);
    if (ok) result.push(node);
    node.children.forEach((child) => walk(child, ok));
  };
  if (tree.root) walk(tree.root, false);
  return result;
}

/** "includes projects from 3 departments". */
export function departmentsText(count) {
  if (count === 0) return "includes no projects yet";
  return `includes projects from ${count} ${count === 1 ? "department" : "departments"}`;
}

/** "Owned by STL › Quality · coordinated by Anna Claes · includes projects from 3 departments". */
export function metaLine(overview, ownerPath) {
  const owner = ownerPath.length ? ownerPath.join(" › ") : overview.owner_name;
  return {
    owner,
    rest: `coordinated by ${overview.coordinator.name} · ${departmentsText(overview.department_count)}`,
  };
}

/** The meter of a days summary: logged and expected as percentages of the plan, 0 to 100. */
export function meter(days) {
  const clamp = (v) => Math.min(100, Math.max(0, v));
  return { logged: clamp(days.logged_percent), expected: clamp(days.expected_percent) };
}

/** "12 / 20 d" for a meter's label; whole or one decimal. */
export function meterText(days) {
  const one = (v) => String(Math.round(v * 10) / 10);
  return `${one(days.logged)} / ${one(days.planned)} d`;
}

/** The years a window covers, for the header of the timeline. */
export function windowYears(window) {
  const first = parseIso(window.start).getUTCFullYear();
  const last = parseIso(window.end).getUTCFullYear();
  return Array.from({ length: last - first + 1 }, (_, i) => first + i);
}

/** Months in a window, for the grid lines. */
export function windowMonths(window) {
  const years = windowYears(window);
  return years.length * 12;
}

/** Status dots of a group: one per project, in status order, at most `limit`. */
export function statusDots(counts, order, limit = 8) {
  const dots = [];
  for (const key of order) {
    for (let i = 0; i < (counts[key] ?? 0); i += 1) dots.push(key);
  }
  return dots.slice(0, limit);
}

/** A feed item's words for what changed: "changed status". */
export function changeText(item) {
  return `changed ${(item.field ?? "").toLowerCase()}`;
}
