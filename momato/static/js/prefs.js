// Per-browser interface state: which panes are collapsed and which tree nodes (SH-1, SH-3).

const KEY = "momato-ui";
const DEFAULTS = { treeCollapsed: true, navCollapsed: false, collapsedNodes: [] };

export function readUi() {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return {
      treeCollapsed: typeof stored?.treeCollapsed === "boolean" ? stored.treeCollapsed : DEFAULTS.treeCollapsed,
      navCollapsed: typeof stored?.navCollapsed === "boolean" ? stored.navCollapsed : DEFAULTS.navCollapsed,
      collapsedNodes: Array.isArray(stored?.collapsedNodes) ? stored.collapsedNodes.filter(Number.isInteger) : [],
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export function writeUi(ui) {
  try {
    localStorage.setItem(KEY, JSON.stringify(ui));
  } catch {
    // blocked storage: collapse states just do not persist
  }
}
