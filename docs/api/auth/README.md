# 多租户身份认证模块 (工业化阶段 1)

设计规范: docs/architecture/MULTI_TENANT_DESIGN.md (权威文档)。SAML 明确延后到阶段 2+。

## 认证 (AuthN)

两种凭证统一换取 principal `{user_id, tenant_id, roles, scopes}`:

* 本地 scoped token — 格式 `sp_<id>_<secret>`。数据库只存
  `token_hash = HMAC-SHA256(SPECPROOF_TOKEN_HMAC_KEY, 完整token)` 与
  `secret_hash = bcrypt(secret)`; token 只展示一次 (show-once)。
* OIDC — 标准 discovery (`OIDC_ISSUER/.well-known/openid-configuration`) +
  JWKS RS256 校验 (PyJWT, iss/aud/exp 严格检查) + role claim 映射
  (`SPECPROOF_OIDC_ROLE_CLAIM`, 默认 `roles`, 未知角色回退 viewer — 最小权限)。

## 授权 (AuthZ) — RBAC 矩阵 (§2, api/identity/principal.py)

| 角色 | jobs | cases/certificates | billing | admin |
|---|---|---|---|---|
| admin | 全 | 全 | 全 | 全 |
| operator | 全 | 读+触发 | 读 | 用户/Token 管理 |
| viewer | 读 | 读 | 无 | 无 |
| auditor | 读(全租户审计视图) | 读+验签 | 读 | 审计视图 |

* 所有 job 查询在 repository 层 (storage/mysql.py + storage/tenant_scope.py)
  自动带 tenant_id 过滤; 跨租户访问一律 404 (与不存在同形, 绝不 403),
  并写 audit 事件 `tenant_isolation_blocked` 带 attempted_tenant。
* tenant_id 只来自 principal (用户行/IdP subject), 请求参数覆盖无效。

## 配置 (全部可选 — 缺省时行为与单租户版本逐字节一致)

| 变量 | 说明 |
|---|---|
| SPECPROOF_AUTH_ENABLED | `true` 开启租户模式 (或设置 OIDC_ISSUER) |
| SPECPROOF_IDENTITY_URL | `''`=内存, `sqlite:<path>`, `mysql://...`; 租户模式默认 `sqlite:specproof_identity.db` |
| SPECPROOF_TOKEN_HMAC_KEY | 本地 token 的 HMAC 密钥 (必填, 无默认值 — fail-closed) |
| SPECPROOF_BCRYPT_ROUNDS | bcrypt 成本, 默认 12 (测试可降到 4) |
| OIDC_ISSUER / OIDC_CLIENT_ID / OIDC_CLIENT_SECRET | OIDC 客户端 |
| SPECPROOF_OIDC_ROLE_CLAIM / SPECPROOF_OIDC_TENANT_CLAIM | claim 名 (默认 roles / tenant_id) |
| SPECPROOF_DEFAULT_TENANT_ID | OIDC 无租户 claim 时的落点租户 |

## 运维引导 (首次建管理员)

```
python -m api.identity.cli init-admin admin@example.com
python -m api.identity.cli mint-token <user_id> --name bootstrap
```

## 数据库迁移

infra/mysql/migrations/0005_tenant_identity.sql (tenants/users/api_tokens +
verification_jobs.tenant_id + audit_logs.attempted_tenant), down 迁移成对存放于
infra/mysql/migrations/down/ (runner 不会自动执行 down 文件)。
MySQL 迁移的 live 验证属集成车道 (本车道无 Docker)。

## 端点

* `GET /auth/config` / `GET /auth/me` — 前端登录页/主体信息
* `GET /auth/oidc/login` → `/auth/oidc/callback` — 授权码流程, id_token 经
  URL fragment 交回 SPA
* `/api/v1/admin/{tenants,users,tokens,audit}` — RBAC 治理的管理面

## 测试

tests/unit/test_tenant_auth.py — 阶段1出口安全测试 (跨租户404+审计、RBAC 矩阵、
OIDC mock JWKS (RS256/过期/错误 issuer)、tenant 参数覆盖无效、兼容模式);
tests/unit/test_identity_store.py — 身份存储 (SQLite/内存, 无 Docker)。
