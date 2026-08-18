import TenantUsers from "./pages/TenantUsers";
import TenantTokens from "./pages/TenantTokens";

// The identity sub-router under /identity/* (same convention as the agent
// console's /agent/* sub-router):
//   /identity          users of the current tenant (list + create + role)
//   /identity/tokens   scoped API tokens (list + mint show-once + revoke)
export default function IdentityApp(props: { seg: string[] }) {
  const rest = props.seg.slice(1);
  if (rest.length === 0) return <TenantUsers />;
  if (rest[0] === "tokens") return <TenantTokens />;
  return <TenantUsers />;
}
