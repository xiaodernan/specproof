import { test } from "node:test";
import assert from "node:assert/strict";

import { changeEmail } from "../src/auth.ts";

test("unauthenticated caller is rejected", () => {
  assert.equal(changeEmail(null, "attacker@evil.com"), "UNAUTHORIZED");
});

test("authenticated user can change email", () => {
  assert.equal(
    changeEmail({ id: "u1", role: "user" }, "new@example.com"),
    "EMAIL_CHANGED:new@example.com"
  );
});
