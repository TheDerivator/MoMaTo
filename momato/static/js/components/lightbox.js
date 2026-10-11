// Images in remarks open full size over the page; any click, or Escape, closes them (RM-2).
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

import { html } from "../html.js";

/** An image in rendered Markdown, unless its author made it a link. */
function zoomableImage(target) {
  const image = target.closest?.(".md img");
  return image && !image.closest("a") ? image : null;
}

/** Mounted once by the app: a click on any Markdown image opens it (Ctrl/⌘ click: a new tab). */
export function Lightbox() {
  const [image, setImage] = useState(null); // { src, alt } while open

  useEffect(() => {
    const onClick = (event) => {
      const found = zoomableImage(event.target);
      if (!found) return;
      event.preventDefault();
      if (event.ctrlKey || event.metaKey || event.shiftKey) window.open(found.src, "_blank", "noopener");
      else setImage({ src: found.src, alt: found.alt });
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return image
    ? html`<${OpenLightbox} key=${image.src} src=${image.src} alt=${image.alt} onClose=${() => setImage(null)} />`
    : null;
}

function OpenLightbox({ src, alt, onClose }) {
  const close = useRef(null);
  useLayoutEffect(() => {
    close.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  // Every click closes it: on the image, beside it, or on the button (there for keyboards).
  return html`<div
    class="lightbox"
    role="dialog"
    aria-modal="true"
    aria-label=${alt ? `Image: ${alt}` : "Image"}
    onClick=${onClose}
  >
    <img class="lightbox__image" src=${src} alt=${alt} />
    <button ref=${close} type="button" class="icon-button lightbox__close" aria-label="Close image">×</button>
  </div>`;
}
