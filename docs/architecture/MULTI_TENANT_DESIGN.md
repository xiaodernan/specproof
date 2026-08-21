# 多租户 + 身份 + RBAC 设计 (工业化阶段 1)

状态: 设计定稿 (2026-08-18) · 现状: CP (Spring Boot) 有 tenant/user 实体与 REST;
Python API 单租户默认; 无 OIDC/RBAC 矩阵。目标: Python API + Web 全链路租户隔离。

## 1. 身份 (AuthN)

- 本地 API Key: 每用户可签发多枚 scoped token (格式 sp_<id>_<secret>),
  数据库只存 HMAC-SHA256(token) 与 secret 哈希 (bcrypt), 展示一次;
- OIDC: 标准 discovery + JWKS 验证 (RS256), 支持 role claim 映射;
  SAML 明确降级为阶段 2+ (行业客户私有化时再启用);
- 两种凭证统一换取 request principal {user_id, tenant_id, roles, scopes}。

## 2. 授权 (AuthZ) — RBAC 矩阵

| 角色 | jobs | cases/certificates | billing | admin |
|---|---|---|---|---|
| admin | 全 | 全 | 全 | 全 |
| operator | 全 | 读+触发 | 读 | 用户/Token 管理 |
| viewer | 读 | 读 | 无 | 无 |
| auditor | 读(全租户审计视图) | 读+验签 | 读 | 无 |

资源级权限: 所有查询强制 tenant_id 过滤; 跨租户访问一律 404 (不暴露存在性),
审计记录拒绝尝试 (audit 事件带 attempted_tenant)。

## 3. 数据模型 (MySQL 迁移)

- tenants(id, name, plan_id, status, created_at);
- users(id, tenant_id, email, oidc_sub?, role, status);
- api_tokens(id, user_id, name, token_hash, secret_hash, scopes, expires_at, last_used_at);
- 迁移必须前向可回滚 (up/down 成对), 用真实 MySQL 状态机测试验证。

## 4. Python API 落地

- api/middleware.py 增 auth 依赖注入: 从 Authorization header 解析 (Bearer sp_* 或
  OIDC JWT) → principal 注入 request.state; 无凭证 → AUTH_REQUIRED (既有稳定码);
- 所有 routes 查询自动带 tenant 过滤 (repository 层参数化, 不靠路由自觉);
- 既有单租户部署模式: 无 auth 配置时维持现状 (兼容), 显式配置开启租户模式。

## 5. 前端 (apps/web)

- 登录页 (本地 token 或 OIDC 重定向), 租户切换器, 用户/Token 管理页;
- 401/403/402 类错误按既有错误码 UI 处理 (TENANT_FORBIDDEN/QUOTA_EXCEEDED)。

## 6. 安全测试 (阶段 1 出口, 全绿才合入)

- 跨租户: A 租户 token 读 B 租户 job id → 404 + 审计事件;
- RBAC: 每角色 × 每资源 矩阵断言 (viewer 写 job → FORBIDDEN);
- OIDC: mock JWKS (RS256) 签名/过期/错误 issuer 用例;
- 注入: tenant_id 来自 principal 而非请求参数 (参数覆盖无效);
- 既有安全门禁 (no-key-leak/bandit/ruff/mypy) 保持全绿。
