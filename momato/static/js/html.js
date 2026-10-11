// The `html` tagged template: htm bound to Preact's h (no build step).
import { h } from "preact";
import htm from "htm";

export const html = htm.bind(h);
