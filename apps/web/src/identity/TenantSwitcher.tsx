import { useEffect, useState } from "react";
import {
  PrincipalInfo,
  getAuthMe,
  listSavedTokens,
  removeSavedToken,
  setBearerToken,
} from "../api";

// Tenant switcher: the active credential IS the tenant context — every
// sp_*/OIDC credential is bound to exactly one tenant server-side, and the
// server never trusts a client-supplied tenant id. Switching = activating a
// different saved token, then re-reading the principal from /auth/me.
export default function TenantSwitcher(props: { onSwitch?: () => void }) {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [saved, setSaved] = useState<ReturnType<typeof listSavedTokens>>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSaved(listSavedTokens());
    getAuthMe()
      .then((me) => setPrincipal(me.principal))
      .catch(() => setPrincipal(null));
  }, []);

  function activate(token: string) {
    setBusy(true);
    setBearerToken(token);
    getAuthMe()
      .then((me) => {
        setPrincipal(me.principal);
        setBusy(false);
        if (props.onSwitch) props.onSwitch();
        window.location.hash = "#/dashboard";
      })
      .catch(() => {
        setBusy(false);
        setPrincipal(null);
      });
  }

  return (
    <div className="tenant-switcher">
      <div className="foot-line">
        当前租户 TENANT — {principal ? principal.tenant_id.slice(0, 8) : "单租户 LEGACY"}
      </div>
      {principal ? (
        <div className="tenant-roles">
          {principal.roles.map((r) => (
            <span key={r} className="pill pill-mute">
              {r}
            </span>
          ))}
        </div>
      ) : null}
      {saved.length > 0 ? (
        <select
          className="tenant-select"
          disabled={busy}
          value=""
          onChange={(e) => {
            if (e.target.value) activate(e.target.value);
          }}
        >
          <option value="">切换租户 Switch…</option>
          {saved.map((s, i) => (
            <option key={i} value={s.token}>
              {s.name}
            </option>
          ))}
        </select>
      ) : null}
      {saved.length > 0 ? (
        <div className="tenant-saved">
          {saved.map((s, i) => (
            <span key={i} className="tenant-saved-row">
              {s.name}
              <button
                className="btn btn-ghost tenant-remove"
                onClick={() => {
                  removeSavedToken(s.token);
                  setSaved(listSavedTokens());
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
