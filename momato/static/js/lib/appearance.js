// Appearance: Light/Dark x Playful/Boring (APP-1, APP-2), remembered per browser.

export const STORAGE_KEY = "momato-appearance";
export const MODES = ["light", "dark"];
export const LOOKS = ["playful", "boring"];
export const DEFAULTS = { mode: null, look: "playful", celebrate: true };

/** What was stored, made safe: unknown values fall back to the defaults. */
export function normalize(stored) {
  const value = stored && typeof stored === "object" ? stored : {};
  return {
    mode: MODES.includes(value.mode) ? value.mode : DEFAULTS.mode,
    look: LOOKS.includes(value.look) ? value.look : DEFAULTS.look,
    celebrate: typeof value.celebrate === "boolean" ? value.celebrate : DEFAULTS.celebrate,
  };
}

/** The mode in force: the chosen one, else what the operating system prefers (APP-2). */
export function resolveMode(appearance, prefersDark) {
  if (appearance.mode) return appearance.mode;
  return prefersDark ? "dark" : "light";
}

export function read(storage) {
  try {
    return normalize(JSON.parse(storage.getItem(STORAGE_KEY) ?? "null"));
  } catch {
    return normalize(null);
  }
}

export function write(storage, appearance) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    // Private windows and blocked storage: the choice just does not persist.
  }
}

/** Put the appearance on the document element (what theme-boot.js does before first paint). */
export function apply(root, appearance, prefersDark) {
  const mode = resolveMode(appearance, prefersDark);
  root.dataset.mode = mode;
  root.dataset.look = appearance.look;
  root.style.colorScheme = mode;
  return mode;
}
