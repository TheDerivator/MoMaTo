// Administration (ADM-1 – ADM-6): which sections a person may open, scope choices, work patterns,
// sign-in names and the wording of the audit log. Pure; the pages only show what comes out.
import { hoursNumber } from "./format.js";
import { pathTo } from "./tree.js";

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export const STATUS_LABELS = {
  active: "Active",
  suspended: "Sign-in suspended",
  deactivated: "Deactivated",
};

/** The sections of the administration a person may open, by what they hold everywhere. */
export function adminSections(permissions) {
  const org = Boolean(permissions["org.manage"]?.everywhere);
  const users = Boolean(permissions["users.manage"]?.everywhere);
  const sections = [];
  if (org) sections.push({ key: "org", label: "Organisation" });
  if (org || users) sections.push({ key: "people", label: "People" });
  if (users) {
    sections.push({ key: "roles", label: "Roles" });
    sections.push({ key: "access", label: "Default access" });
    sections.push({ key: "sso", label: "Single sign-on" });
    sections.push({ key: "audit", label: "Audit log" });
  }
  return sections;
}

/** The section to show: the one asked for when allowed, else the first. */
export function chosenSection(sections, wanted) {
  return sections.find((s) => s.key === wanted) ?? sections[0] ?? null;
}

// ------------------------------------------------------------------ scopes

/** "global", "own_department" or "node:12": one value for a select. */
export function scopeValue(kind, nodeId) {
  return kind === "node" ? `node:${nodeId}` : kind;
}

export function parseScope(value) {
  if (value.startsWith("node:")) return { scope_kind: "node", node_id: Number(value.slice(5)) };
  return { scope_kind: value, node_id: null };
}

/** The choices of a scope select: everywhere, own department, then every node below the root. */
export function scopeOptions(tree) {
  const options = [
    { value: "global", label: "Everywhere" },
    { value: "own_department", label: "Own department" },
  ];
  const walk = (node) => {
    for (const child of node.children) {
      const names = pathTo(tree, child.id).slice(1).map((n) => n.name);
      options.push({ value: `node:${child.id}`, label: names.join(" › ") });
      walk(child);
    }
  };
  if (tree.root) walk(tree.root);
  return options;
}

// ------------------------------------------------------------------ work patterns

/** Hours text of minutes: "8", "7.5". */
export function hoursField(minutes) {
  return hoursNumber(minutes);
}

/** Minutes of an hours text ("7.5", "7,5", "7:30", "8"); null when it is not a duration. */
export function minutesFromText(text) {
  const value = String(text).trim().replace(",", ".");
  if (value === "") return null;
  const clock = /^(\d{1,2}):([0-5]\d)$/.exec(value);
  if (clock) return Number(clock[1]) * 60 + Number(clock[2]);
  if (!/^\d{1,2}(\.\d{1,2})?$/.test(value)) return null;
  const minutes = Math.round(Number(value) * 60);
  return minutes <= 12 * 60 ? minutes : null;
}

/** The five minutes of five texts, or null when one is not valid. */
export function patternFromTexts(texts) {
  const minutes = texts.map(minutesFromText);
  return minutes.some((m) => m === null) ? null : minutes;
}

/** "40 h a week", or "32 h a week: Mon–Thu 8 h" when the days differ from the first. */
export function patternSummary(minutes) {
  const total = minutes.reduce((sum, m) => sum + m, 0);
  const week = `${hoursNumber(total)} h a week`;
  if (minutes.every((m) => m === minutes[0])) {
    return minutes[0] === 0 ? week : `${week} (${hoursNumber(minutes[0])} h a day)`;
  }
  const days = minutes.map((m, i) => `${WEEKDAYS[i]} ${hoursNumber(m)}`).join(", ");
  return `${week} (${days})`;
}

/** Days with one decimal at most: "220", "176", "188.5". */
export function daysText(days) {
  return String(Math.round(days * 100) / 100);
}

// ------------------------------------------------------------------ sign-in names

const SPECIAL = { ß: "ss", ø: "o", æ: "ae", œ: "oe", ł: "l", đ: "d", ð: "d", þ: "th" };

/** The server's default login name for a person: "Chloé Martens" → "chloe.martens". */
export function suggestUsername(name) {
  const folded = [...name.toLowerCase()].map((c) => SPECIAL[c] ?? c).join("");
  const ascii = folded.normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
  const words = ascii.replace(/[^a-z0-9]+/g, ".").replace(/^\.+|\.+$/g, "");
  return words.slice(0, 90).replace(/\.+$/, "") || "user";
}

// ------------------------------------------------------------------ the audit log

const ACTIONS = {
  "auth.login": "Signed in",
  "user.created": "Account created",
  "user.admin_reset": "Administrator account reset",
  "user.password_changed": "Changed own password",
  "user.password_reset": "Password reset",
  "user.role_granted": "Role granted",
  "user.role_revoked": "Role revoked",
  "user.status_changed": "Status changed",
  "user.sign_in_changed": "Sign-in changed",
  "person.created": "Person added",
  "person.updated": "Person changed",
  "person.availability_set": "Availability set",
  "person.availability_cleared": "Availability cleared",
  "org.node_created": "Branch added",
  "org.node_updated": "Branch changed",
  "org.node_deleted": "Branch deleted",
  "role.created": "Role created",
  "role.updated": "Role changed",
  "role.deleted": "Role deleted",
  "access.default_granted": "Default access granted",
  "access.default_revoked": "Default access removed",
  "access.group_mapped": "Group mapped to a role",
  "access.group_unmapped": "Group mapping removed",
  "user.sso_linked": "Signed in through SSO for the first time",
  "user.sso_created": "Account created by SSO",
  "token.created": "API token created",
  "token.revoked": "API token revoked",
};

/** Words for an action key; unknown ones are made readable: "plan.moved" → "Plan moved". */
export function actionLabel(action) {
  if (ACTIONS[action]) return ACTIONS[action];
  const words = action.replace(/[._]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The details of an entry as "key: value · key: value". */
export function detailsText(details) {
  return Object.entries(details ?? {})
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${typeof value === "object" ? JSON.stringify(value) : value}`)
    .join(" · ");
}
