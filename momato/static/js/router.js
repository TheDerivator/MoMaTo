// History API router under the page's base path (SH-8): the current route, navigation, links.
import { useEffect, useState } from "preact/hooks";

import { html } from "./html.js";
import { parseRoute, relativePath } from "./lib/routes.js";

const basePath = () => new URL(document.baseURI).pathname;
const listeners = new Set();

export function currentRoute() {
  return parseRoute(relativePath(location.pathname, basePath()), location.search);
}

/** Go to a link relative to the base ("projects?node=3"). */
export function navigate(url, { replace = false } = {}) {
  const target = new URL(url, document.baseURI);
  const same = target.pathname + target.search === location.pathname + location.search;
  if (same) return;
  history[replace ? "replaceState" : "pushState"]({}, "", target);
  listeners.forEach((listener) => listener());
}

/** The route object that follows the address bar. */
export function useRoute() {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const update = () => setRoute(currentRoute());
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return route;
}

function plainClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

/** A real link (so Ctrl/middle click open a new tab, PL-5) that navigates without a reload. */
export function Link({ href, children, onNavigate, ...attributes }) {
  const onClick = (event) => {
    if (event.defaultPrevented || !plainClick(event)) return;
    event.preventDefault();
    navigate(href);
    onNavigate?.();
  };
  return html`<a href=${href} onClick=${onClick} ...${attributes}>${children}</a>`;
}
