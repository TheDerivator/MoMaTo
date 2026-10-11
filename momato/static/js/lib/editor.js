// Text operations of the Markdown composer (bold, lists, inserted images). Pure: each returns the
// new text and selection, so the component only has to apply them. Ported from TaskBoard.

/** The remark template (RM-1): Done and Next steps, ready to fill in. */
export const TEMPLATE = "Done:\n- \n\nNext steps:\n- ";

/** Surround the selection (or a placeholder) with markers: `**bold**`, `_italic_`, `` `code` ``. */
export function wrap(value, start, end, before, after = before, placeholder = "") {
  const selected = value.slice(start, end) || placeholder;
  const text = value.slice(0, start) + before + selected + after + value.slice(end);
  return { text, start: start + before.length, end: start + before.length + selected.length };
}

/** Prefix every line touched by the selection, e.g. "- " for a bulleted list. */
export function prefixLines(value, start, end, prefix) {
  const lineStart = value.lastIndexOf("\n", start - 1) + 1;
  const block = value.slice(lineStart, end);
  const replaced = block
    .split("\n")
    .map((line) => prefix + line)
    .join("\n");
  const text = value.slice(0, lineStart) + replaced + value.slice(end);
  return { text, start: start + prefix.length, end: end + (replaced.length - block.length) };
}

/** The end of the line that contains `position` (where a new block can go without splitting text). */
export function lineEnd(value, position) {
  const next = value.indexOf("\n", position);
  return next === -1 ? value.length : next;
}

/** Insert a block (e.g. an image) on its own line at the position. */
export function insertBlock(value, position, block) {
  const before = value.slice(0, position);
  const after = value.slice(position);
  const lead = before && !before.endsWith("\n") ? "\n" : "";
  const trail = after && !after.startsWith("\n") ? "\n" : "";
  const caret = (before + lead + block).length;
  return { text: before + lead + block + trail + after, start: caret, end: caret };
}

/** Remove every occurrence of a fragment (e.g. an image's Markdown), with the line break after it. */
export function removeFragment(value, fragment) {
  return value.split(`${fragment}\n`).join("").split(fragment).join("");
}

/** The template after the text so far: on its own paragraph, never over what was written. */
export function withTemplate(value) {
  if (!value.trim()) return { text: TEMPLATE, start: "Done:\n- ".length, end: "Done:\n- ".length };
  const separator = value.endsWith("\n\n") ? "" : value.endsWith("\n") ? "\n" : "\n\n";
  const text = value + separator + TEMPLATE;
  const caret = value.length + separator.length + "Done:\n- ".length;
  return { text, start: caret, end: caret };
}
