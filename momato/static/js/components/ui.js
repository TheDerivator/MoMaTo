// Small shared components: avatars, status pills, a click-outside hook, the toast stack.
import { useLayoutEffect } from "preact/hooks";

import { html } from "../html.js";
import { initials } from "../lib/format.js";

/** A person's circle with their initials, in their colour. */
export function Avatar({ person, size = 26, ring = false, title }) {
  const style = { "--hue": person.hue, "--size": `${size}px` };
  return html`<span
    class=${`avatar${ring ? " avatar--ring" : ""}`}
    style=${style}
    title=${title ?? person.name}
    aria-hidden=${title === undefined ? "true" : undefined}
    >${initials(person.name)}</span
  >`;
}

/** "via Claude Code": written through an API token (TOK-3). */
export function ViaBadge({ via }) {
  if (!via) return null;
  return html`<span class="via-badge" title=${`Done through the API token “${via}”`}>via ${via}</span>`;
}

/** The status pill: dot and label in the status colour. */
export function StatusPill({ status }) {
  return html`<span
    class=${`status-pill${status.gray ? " status-pill--gray" : ""}`}
    style=${{ "--hue": status.hue }}
  >
    <span class=${`dot${status.gray ? " dot--gray" : ""}`} style=${{ "--hue": status.hue }}></span>
    ${status.label}
  </span>`;
}

/** Close a popover on a click outside it and on Escape. */
export function useDismiss(ref, active, onClose) {
  useLayoutEffect(() => {
    if (!active) return undefined;
    const onPointer = (event) => {
      if (ref.current && !ref.current.contains(event.target)) onClose();
    };
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref, active, onClose]);
}

/** Toasts: errors and confirmations that roll back optimistic changes (SH-10). */
export function Toasts({ toasts }) {
  return html`<div class="toasts" role="status" aria-live="polite">
    ${toasts.map((t) => html`<div key=${t.id} class=${`toast${t.kind === "error" ? " toast--error" : ""}`}>${t.text}</div>`)}
  </div>`;
}
