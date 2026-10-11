// Administration › Organisation: the tree editor (ADM-1): add, rename, flag, move, reorder, delete.
import { useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ConfirmDialog } from "../components/dialogs.js";
import { html } from "../html.js";
import { subtreeIds, treeRows } from "../lib/tree.js";

/** A node's rows: the tree flattened with every branch open. */
function rowsOf(tree) {
  return treeRows(tree, new Set(), {}).map((row) => ({ ...row, node: tree.nodes.get(row.id) }));
}

function NodeRow({ ctx, row, siblings, onChange, onAsk }) {
  const { tree, toast } = ctx;
  const { node } = row;
  const isRoot = node.parent_id === null;
  const [name, setName] = useState(node.name);
  const [adding, setAdding] = useState(false);
  const [child, setChild] = useState("");
  const index = siblings.findIndex((s) => s.id === node.id);
  const below = new Set(subtreeIds(tree, node.id));

  const call = async (request, message) => {
    try {
      await request();
      await onChange();
      if (message) toast(message);
      return true;
    } catch (failure) {
      toast(messageOf(failure), "error");
      setName(node.name);
      return false;
    }
  };
  const patch = (body, message) => call(() => api(`admin/org/${node.id}`, { method: "PATCH", body }), message);

  const rename = () => {
    const text = name.trim();
    if (text && text !== node.name) patch({ name: text });
    else setName(node.name);
  };
  const add = async (event) => {
    event.preventDefault();
    const text = child.trim();
    if (!text) return;
    const ok = await call(
      () => api("admin/org", { method: "POST", body: { parent_id: node.id, name: text } }),
      `Added ${text}.`,
    );
    if (ok) {
      setChild("");
      setAdding(false);
    }
  };

  return html`<li class="org-row" style=${{ "--depth": row.depth }}>
    <div class="org-row__line">
      <input
        class="input org-row__name"
        aria-label=${`Name of ${node.name}`}
        value=${name}
        maxlength="200"
        onInput=${(e) => setName(e.target.value)}
        onBlur=${rename}
        onKeyDown=${(e) => {
          if (e.key === "Enter") e.target.blur();
          if (e.key === "Escape") setName(node.name);
        }}
      />
      <label class="check-row org-row__department">
        <input
          type="checkbox"
          checked=${node.is_department}
          onChange=${(e) => patch({ is_department: e.target.checked })}
        />
        Department
      </label>
      <span class="org-row__tools">
        ${isRoot
          ? html`<span class="muted">Root</span>`
          : html`
              <button
                type="button"
                class="icon-button"
                aria-label=${`Move ${node.name} up`}
                disabled=${index <= 0}
                onClick=${() => patch({ position: index - 1 })}
              >↑</button>
              <button
                type="button"
                class="icon-button"
                aria-label=${`Move ${node.name} down`}
                disabled=${index === siblings.length - 1}
                onClick=${() => patch({ position: index + 1 })}
              >↓</button>
              <select
                class="select org-row__parent"
                aria-label=${`Move ${node.name} under`}
                value=${node.parent_id}
                onChange=${(e) => patch({ parent_id: Number(e.target.value) }, `Moved ${node.name}.`)}
              >
                ${rowsOf(tree)
                  .filter((r) => !below.has(r.id))
                  .map(
                    (r) => html`<option key=${r.id} value=${r.id} selected=${r.id === node.parent_id}>
                      ${"– ".repeat(r.depth)}${r.name}
                    </option>`,
                  )}
              </select>
            `}
        <button type="button" class="btn btn--ghost" onClick=${() => setAdding(!adding)} aria-expanded=${adding ? "true" : "false"}>
          + Branch
        </button>
        ${isRoot
          ? null
          : html`<button type="button" class="btn btn--ghost btn--danger" onClick=${() => onAsk(node)} aria-label=${`Delete ${node.name}`}>
              Delete
            </button>`}
      </span>
    </div>
    ${adding
      ? html`<form class="org-row__add" onSubmit=${add}>
          <input
            class="input"
            aria-label=${`New branch under ${node.name}`}
            placeholder="Name of the new branch"
            value=${child}
            maxlength="200"
            required
            autofocus
            onInput=${(e) => setChild(e.target.value)}
          />
          <button type="submit" class="btn btn--dark">Add</button>
        </form>`
      : null}
  </li>`;
}

export function OrgEditor({ ctx }) {
  const { tree, toast } = ctx;
  const [asking, setAsking] = useState(null);
  const rows = rowsOf(tree);
  const siblingsOf = (row) => (row.node.parent_id === null ? [row.node] : tree.nodes.get(row.node.parent_id).children);

  const remove = async () => {
    const node = asking;
    try {
      await api(`admin/org/${node.id}`, { method: "DELETE" });
      await ctx.reload();
      toast(`Deleted ${node.name}.`);
    } catch (failure) {
      toast(messageOf(failure), "error");
    }
  };

  return html`<section class="card admin-card" aria-label="Organisation tree">
    <p class="muted admin-note">
      A branch flagged as a <b>department</b> is what "own department" means for the people below it, and the
      unit of project administration. Branches are deleted only when nothing refers to them.
    </p>
    <ul class="org-tree">
      ${rows.map(
        (row) => html`<${NodeRow}
          key=${row.id}
          ctx=${ctx}
          row=${row}
          siblings=${siblingsOf(row)}
          onChange=${() => ctx.reload()}
          onAsk=${setAsking}
        />`,
      )}
    </ul>
    ${asking
      ? html`<${ConfirmDialog}
          title=${`Delete “${asking.name}”?`}
          confirmLabel="Delete branch"
          onClose=${() => setAsking(null)}
          onConfirm=${remove}
        >
          <p>The branch goes away. It must have no branches, people, projects, plans or rights.</p>
        <//>`
      : null}
  </section>`;
}
