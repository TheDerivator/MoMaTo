// The "not found or no access" page (SH-11).
import { html } from "../html.js";
import { Link } from "../router.js";

export function NotFound() {
  return html`<div class="placeholder">
    <h1>Not found or no access</h1>
    <p class="muted">This page does not exist, or you may not see it.</p>
    <${Link} href="projects">Back to Projects<//>
  </div>`;
}
