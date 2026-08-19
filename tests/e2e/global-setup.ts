import { readFileSync } from "node:fs";
import path from "node:path";

// One-time identity provisioning for the permissions scenario. The fixture
// bootstraps exactly ONE admin credential (tenant + admin user + show-once
// sp_* token); everything else — the viewer user and its token — is created
// here through the REAL /api/v1/admin/* HTTP endpoints so the RBAC path the
// scenario asserts on is the production one.

interface FixtureState {
  api_base: string;
  admin_token: string;
  admin_email: string;
  viewer_email: string;
  job_id: string;
}

interface UserRow {
  id: string;
  email: string;
  role: string;
}

export default async function globalSetup(): Promise<void> {
  const statePath = path.join(__dirname, ".state", "e2e-state.json");
  const state = JSON.parse(readFileSync(statePath, "utf8")) as FixtureState;
  const headers: Record<string, string> = {
    Authorization: "Bearer " + state.admin_token,
    "Content-Type": "application/json",
  };

  const listResp = await fetch(state.api_base + "/api/v1/admin/users", { headers });
  if (!listResp.ok) {
    throw new Error("global-setup: list users failed: " + (await listResp.text()));
  }
  const listBody = (await listResp.json()) as { users: UserRow[] };
  let viewer = listBody.users.find((u) => u.email === state.viewer_email);
  if (!viewer) {
    const createResp = await fetch(state.api_base + "/api/v1/admin/users", {
      method: "POST",
      headers,
      body: JSON.stringify({ email: state.viewer_email, role: "viewer" }),
    });
    if (!createResp.ok) {
      throw new Error("global-setup: create viewer failed: " + (await createResp.text()));
    }
    const created = (await createResp.json()) as { user: UserRow };
    viewer = created.user;
  }

  const mintResp = await fetch(state.api_base + "/api/v1/admin/tokens", {
    method: "POST",
    headers,
    body: JSON.stringify({ name: "e2e-viewer", user_id: viewer.id }),
  });
  if (!mintResp.ok) {
    throw new Error("global-setup: mint viewer token failed: " + (await mintResp.text()));
  }
  const mintBody = (await mintResp.json()) as { cleartext: string };

  process.env.E2E_ADMIN_TOKEN = state.admin_token;
  process.env.E2E_ADMIN_EMAIL = state.admin_email;
  process.env.E2E_VIEWER_TOKEN = mintBody.cleartext;
  process.env.E2E_VIEWER_EMAIL = state.viewer_email;
  process.env.E2E_JOB_ID = state.job_id;
  process.env.E2E_API_BASE = state.api_base;
}
