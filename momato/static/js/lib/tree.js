// The organisation tree: branches, breadcrumbs, the rows of the tree pane (SH-3, SH-5).

/** Index the flat `org` list of the bootstrap: parents, children in order, depth. */
export function buildTree(org) {
  const nodes = new Map();
  for (const n of org) nodes.set(n.id, { ...n, children: [], depth: 0 });
  let root = null;
  for (const n of org) {
    const node = nodes.get(n.id);
    const parent = n.parent_id === null ? null : nodes.get(n.parent_id);
    if (parent) parent.children.push(node);
    else root = node;
  }
  const sortKids = (node) => {
    node.children.sort((a, b) => a.position - b.position || a.id - b.id);
    for (const child of node.children) {
      child.depth = node.depth + 1;
      sortKids(child);
    }
  };
  if (root) sortKids(root);
  return { nodes, root };
}

/** The ids of a node and everything below it. */
export function subtreeIds(tree, id) {
  const found = [];
  const walk = (node) => {
    found.push(node.id);
    node.children.forEach(walk);
  };
  const start = tree.nodes.get(id);
  if (start) walk(start);
  return found;
}

/** Nodes from the root down to `id`, inclusive. */
export function pathTo(tree, id) {
  const path = [];
  for (let node = tree.nodes.get(id); node; node = tree.nodes.get(node.parent_id)) path.unshift(node);
  return path;
}

/**
 * The rows of the tree pane: every node whose ancestors are all expanded, with its depth,
 * whether it has children, whether it is expanded and its count.
 */
export function treeRows(tree, collapsed, counts) {
  const rows = [];
  const walk = (node) => {
    const expanded = !collapsed.has(node.id);
    rows.push({
      id: node.id,
      name: node.name,
      depth: node.depth,
      hasChildren: node.children.length > 0,
      expanded,
      count: counts[node.id] ?? 0,
    });
    if (expanded) node.children.forEach(walk);
  };
  if (tree.root) walk(tree.root);
  return rows;
}

/**
 * The breadcrumb of a selected node (SH-5): its ancestors below the root as buttons, the node
 * as the title, and the child menu with the view's counts.
 */
export function breadcrumb(tree, id, counts) {
  const path = pathTo(tree, id);
  const current = path[path.length - 1] ?? tree.root;
  return {
    ancestors: path.slice(0, -1).map((n) => ({ id: n.id, name: n.name })),
    current: current ? { id: current.id, name: current.name } : null,
    kids: (current?.children ?? []).map((k) => ({
      id: k.id,
      name: k.name,
      count: counts[k.id] ?? 0,
      hasChildren: k.children.length > 0,
    })),
  };
}

/** The selected node's name for the collapsed rail; the root reads as the organisation. */
export function nodeLabel(tree, id) {
  return tree.nodes.get(id)?.name ?? "";
}
