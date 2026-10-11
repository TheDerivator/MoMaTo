// The celebration after submitting a week (TS-11): a blurred backdrop, confetti and a modal.
import { useEffect, useMemo, useRef } from "preact/hooks";

import { html } from "../html.js";
import { formatHours } from "../lib/format.js";

const PIECES = 70;
const HUES = [285, 155, 235, 60, 330, 25];

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** Confetti pieces with their own start, drift, spin, colour and fall time (1.8 – 3.4 s). */
function confettiPieces(random = Math.random) {
  return Array.from({ length: PIECES }, (_, index) => ({
    id: index,
    left: random() * 100,
    duration: 1.8 + random() * 1.6,
    delay: random() * 0.5,
    drift: (random() - 0.5) * 240,
    spin: 360 + random() * 720,
    hue: HUES[index % HUES.length],
    width: 6 + random() * 6,
    height: 8 + random() * 8,
  }));
}

export function Celebration({ summary, totalMinutes, targetMinutes, onClose }) {
  const reduced = prefersReducedMotion();
  const pieces = useMemo(() => (reduced ? [] : confettiPieces()), [reduced]);
  const close = useRef(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const percent = Math.min(100, Math.round((totalMinutes / Math.max(1, targetMinutes)) * 100));
  return html`<div class="celebration" role="dialog" aria-modal="true" aria-labelledby="celebration-title">
    <div class="celebration__confetti" aria-hidden="true">
      ${pieces.map(
        (p) => html`<span
          key=${p.id}
          class="confetti__piece"
          style=${{
            left: `${p.left}%`,
            width: `${p.width}px`,
            height: `${p.height}px`,
            "--hue": p.hue,
            "--drift": `${p.drift}px`,
            "--spin": `${p.spin}deg`,
            animationDuration: `${p.duration}s`,
            animationDelay: `${p.delay}s`,
          }}
        ></span>`,
      )}
    </div>
    <div class=${`celebration__modal${reduced ? " celebration__modal--still" : ""}`}>
      <div class="ts-ring ts-ring--big" style=${{ "--pct": percent }}>
        <div class="ts-ring__inner">
          <span class="ts-ring__hours">${formatHours(totalMinutes).replace(/ h$/, "")}h</span>
        </div>
      </div>
      <h2 id="celebration-title" class="celebration__title">${summary.headline}</h2>
      <p class="celebration__summary">${summary.summary}</p>
      <div class="celebration__chips">
        ${summary.chips.map(
          (chip) => html`<span key=${chip.key} class="celebration__chip">
            ${chip.name} <b>${formatHours(chip.booked).replace(/ h$/, "")}/${formatHours(Math.round(chip.planned / 60) * 60).replace(/ h$/, "")}</b>
          </span>`,
        )}
      </div>
      <button ref=${close} type="button" class="btn btn--accent celebration__close" onClick=${onClose}>
        Back to work
      </button>
    </div>
  </div>`;
}
