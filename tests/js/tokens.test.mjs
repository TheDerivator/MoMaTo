// Unit tests for static/js/lib/tokens.js: the choices, expiry and use wording, "via", the commands.
// [TOK-1] [TOK-3]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_EXPIRY, EXPIRY_CHOICES, SCOPES, envCommands, expiryText, lastUsedText, nameVia, scopeLabel,
} from "../../momato/static/js/lib/tokens.js";

test("[TOK-1] a token's expiry and last use", () => {
  assert.equal(expiryText({ expires_at: null, expired: false }), "Never expires");
  assert.equal(expiryText({ expires_at: "2027-01-04T12:00:00Z", expired: false }), "Expires 4 Jan 2027");
  assert.equal(expiryText({ expires_at: "2026-01-04T12:00:00Z", expired: true }), "Expired 4 Jan 2026");
  assert.equal(lastUsedText({ last_used_at: null }), "Never used");
  assert.equal(lastUsedText({ last_used_at: "2026-10-03T12:02:00Z" }), "Last used 3 Oct 2026");
});

test("[TOK-1] the choices for a new token", () => {
  assert.deepEqual(SCOPES.map((s) => s.value), ["read", "write"]);
  assert.equal(scopeLabel("read"), "Read only");
  assert.equal(scopeLabel("write"), "Read and write");
  assert.equal(scopeLabel("other"), "other");
  assert.ok(EXPIRY_CHOICES.some((c) => c.days === DEFAULT_EXPIRY));
  assert.equal(EXPIRY_CHOICES.at(-1).days, null); // "Never" is the person's choice to make
});

test("[TOK-3] what a token did names the token", () => {
  const anna = { name: "Anna Claes" };
  assert.equal(nameVia(anna, null), "Anna Claes");
  assert.equal(nameVia(anna, undefined), "Anna Claes");
  assert.equal(nameVia(anna, "Claude Code"), "Anna Claes via Claude Code");
});

test("the commands put the token where the agent guide says to look", () => {
  assert.deepEqual(
    envCommands("mm_abc-_9").map((c) => c.command),
    ['$env:MOMATO_TOKEN = "mm_abc-_9"', 'setx MOMATO_TOKEN "mm_abc-_9"', "export MOMATO_TOKEN='mm_abc-_9'"],
  );
});
