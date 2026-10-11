// The breadcrumb title of a view that follows the organisation tree: eyebrow, ancestors as ghost
// buttons, the current node as H1 and a menu of its children with the view's counts (SH-5).
import { useRef, useState } from "preact/hooks";

import { html } from "../html.js";
import { breadcrumb } from "../lib/tree.js";
import { useDismiss } from "./ui.js";

/** `nodeCounts`: id → the view's count per node; `onGo(id)` goes to a node (root: the whole). */
export function Crumbs({ ctx, eyebrow, nodeId, nodeCounts, onGo }) {
  const { tree } = ctx;
  const crumb = breadcrumb(tree, nodeId ?? tree.root.id, nodeCounts ?? {});
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));

  const go = (id) => {
    setOpen(false);
    onGo(id);
  };
  return html`<div class="crumbs">
    <span class="eyebrow">${eyebrow}</span>
    <div class="crumbs__trail">
      ${crumb.ancestors.map(
        (a) => html`<button key=${a.id} class="crumbs__ancestor" title=${a.name} onClick=${() => go(a.id)}>${a.name}</button>
          <span class="crumbs__separator" aria-hidden="true">/</span>`,
      )}
      <div class="crumbs__current popover-anchor" ref=${ref}>
        <h1 class="crumbs__title">${crumb.current?.name}</h1>
        ${crumb.kids.length
          ? html`<button
              class="crumbs__menu-button"
              title="Go to a sub-department"
              aria-label=${`Inside ${crumb.current?.name}`}
              aria-haspopup="menu"
              aria-expanded=${open ? "true" : "false"}
              onClick=${() => setOpen(!open)}
            >
              ▾
            </button>`
          : null}
        ${open
          ? html`<div class="popover popover--below" role="menu">
              <span class="popover__title">Inside ${crumb.current?.name}</span>
              ${crumb.kids.map(
                (k) => html`<button key=${k.id} class="menu-item" role="menuitem" onClick=${() => go(k.id)}>
                  <span class="menu-item__name">${k.name}</span>
                  <span class="menu-item__count">${k.count}</span>
                  <span class="menu-item__chevron" aria-hidden="true">${k.hasChildren ? "›" : ""}</span>
                </button>`,
              )}
            </div>`
          : null}
      </div>
    </div>
  </div>`;
}
