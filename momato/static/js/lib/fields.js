// Detail fields of the All details tab (DT-1 – DT-3): how each type is shown, and how an input's
// text becomes the value the server validates (mirrors momato/domain/fields.py).
import { formatDate } from "./format.js";

export const MAX_TEXT = 300;
export const MAX_LONG_TEXT = 10_000;
export const MAX_TAGS = 20;
export const MAX_TAG = 50;

/** The kind of editor a field needs. */
export function editorKind(field) {
  switch (field.type) {
    case "long_text":
      return "textarea";
    case "number":
      return "number";
    case "date":
      return "date";
    case "choice":
      return "choice";
    case "tags":
      return "tags";
    case "person":
      return "person";
    case "project":
      return "project";
    case "yes_no":
      return "yesno";
    default:
      return "text";
  }
}

export function isEmpty(value) {
  return value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
}

/** The value as text: people and projects are looked up (`lookup.people`, `lookup.projects`). */
export function displayValue(field, value, lookup = {}) {
  if (isEmpty(value)) return "";
  switch (field.type) {
    case "date":
      return formatDate(value);
    case "tags":
      return value.join(", ");
    case "yes_no":
      return value ? "Yes" : "No";
    case "person":
      return lookup.people?.get(value)?.name ?? `Person ${value}`;
    case "project": {
      const project = lookup.projects?.get(value);
      return project ? `#${value} ${project.name}` : `#${value}`;
    }
    default:
      return String(value);
  }
}

/** Tags typed as "a, b ,c": trimmed, no empty ones, no case-insensitive duplicates. */
export function parseTags(text) {
  const seen = new Set();
  const tags = [];
  for (const part of text.split(",")) {
    const tag = part.trim();
    if (tag && !seen.has(tag.toLowerCase())) {
      seen.add(tag.toLowerCase());
      tags.push(tag);
    }
  }
  return tags;
}

/**
 * The value to send for what was typed: `{ value }` (null clears the field) or `{ error }`.
 * Choices, yes/no, people and projects come from pickers and are passed through.
 */
export function parseInput(field, text) {
  const trimmed = typeof text === "string" ? text.trim() : text;
  if (isEmpty(trimmed)) return { value: null };
  switch (field.type) {
    case "text":
      return trimmed.length > MAX_TEXT
        ? { error: `${field.label} is longer than ${MAX_TEXT} characters` }
        : { value: trimmed };
    case "long_text":
      return trimmed.length > MAX_LONG_TEXT
        ? { error: `${field.label} is longer than ${MAX_LONG_TEXT} characters` }
        : { value: trimmed };
    case "number": {
      const number = Number(String(trimmed).replace(",", "."));
      return Number.isFinite(number) ? { value: number } : { error: "must be a number" };
    }
    case "date":
      return /^\d{4}-\d{2}-\d{2}$/.test(trimmed) ? { value: trimmed } : { error: "must be a date" };
    case "tags": {
      const tags = Array.isArray(trimmed) ? trimmed : parseTags(trimmed);
      if (tags.length > MAX_TAGS) return { error: `at most ${MAX_TAGS} tags` };
      if (tags.some((t) => t.length > MAX_TAG)) return { error: `a tag is longer than ${MAX_TAG} characters` };
      return { value: tags.length ? tags : null };
    }
    default:
      return { value: trimmed };
  }
}

/** Whether two values are the same, so an unchanged edit sends nothing. */
export function sameValue(a, b) {
  if (isEmpty(a) && isEmpty(b)) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => item === b[i]);
  }
  return a === b;
}

/** The text an editor starts with. */
export function editorText(field, value) {
  if (isEmpty(value)) return "";
  if (field.type === "tags") return value.join(", ");
  return String(value);
}

/** Project numbers referred to by the project-type fields of the cards (to look their names up). */
export function referencedProjects(cards, details) {
  const numbers = new Set();
  for (const card of cards) {
    for (const field of card.fields) {
      if (field.type === "project" && Number.isInteger(details[field.key])) numbers.add(details[field.key]);
    }
  }
  return [...numbers];
}
