// API tokens for AI agents (TOK-1, pure): the choices for a new token, what the profile page says
// about each one, how a token's work is credited ("via") and the commands that hand one to an agent.
import { formatDate } from "./format.js";

export const SCOPES = [
  { value: "read", label: "Read only", hint: "Look things up, summarise, report. Cannot change anything." },
  {
    value: "write",
    label: "Read and write",
    hint: "Also edit projects, remarks, plans and your time, as you could. Never administration.",
  },
];

export const EXPIRY_CHOICES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
  { days: null, label: "Never" },
];

export const DEFAULT_EXPIRY = 90;

export function scopeLabel(scope) {
  return SCOPES.find((s) => s.value === scope)?.label ?? scope;
}

/** "Expires 4 Jan 2027", "Expired 4 Jan 2027" or "Never expires". */
export function expiryText(token) {
  if (!token.expires_at) return "Never expires";
  const day = formatDate(token.expires_at.slice(0, 10));
  return token.expired ? `Expired ${day}` : `Expires ${day}`;
}

/** "Never used" or "Last used 3 Oct 2026". */
export function lastUsedText(token) {
  return token.last_used_at ? `Last used ${formatDate(token.last_used_at.slice(0, 10))}` : "Never used";
}

/** "Anna Claes", or "Anna Claes via Claude Code" for what was done through an API token. */
export function nameVia(person, via) {
  return via ? `${person.name} via ${via}` : person.name;
}

/** Commands that put a new token in MOMATO_TOKEN, where the agent guide tells agents to look. */
export function envCommands(secret) {
  return [
    { shell: "PowerShell, this window", command: `$env:MOMATO_TOKEN = "${secret}"` },
    { shell: "Windows, every new window", command: `setx MOMATO_TOKEN "${secret}"` },
    { shell: "bash or zsh", command: `export MOMATO_TOKEN='${secret}'` },
  ];
}
