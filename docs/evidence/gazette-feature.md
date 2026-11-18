# Gazette Feature — 2026-11-18T12:06:43+00:00

**anchor:** #2002 《问之有答》：问问书 · Ask the Book —— 公开 · 匿名 · 限流 · 指纹缓存 · 模型不得审判 · zh+en · 61 routes · chronicle **1798** · worldbook **203 卷（双语对称）** · UI **598/598**  ·  **model:** gpt-6.1-terra

## 中文 · 一闪 \n\n这一天，书开出一条公开、匿名、限流的问答车道：任何人都可提问，模型先读整部世界书；书里没写，就答“书里没写”，不判决、不涂绿，也不发明数字。它落在 `/worldbook/ask` 和 Ask the Book 页面，带指纹缓存，与观察车道并列为公开只读入口。账面上，worldbook 增至203卷，chronicle记至1798，io 的 chips 由60自动增至61；court 仍 LOCKED，Night Watch 仍 CRACKED，24枚 pinned reds 仍在册。\n\n## English

「问问书」的模型车道落在 api/worldbook_ask.py：模型读完整部世界书后作答，不裁判，也不补造数字、起源、日期或人物；书中未载，便说「书里没写」。公开的 POST /worldbook/ask 落在 api/routes/worldbook_ask.py，由 api/server.py 挂载，api/middleware.py 将 /worldbook/ 纳入公开只读前缀，限流与指纹缓存设在路由层。双语界面落在 apps/web/src/pages/AskTheBook.tsx 与 i18n/strings.ts；AskTheBook.test.tsx 为 4/4，全量 UI 为 598/598。于是，这个世界向匿名来客开放提问，却不把回答授为判决。它的边界仍清楚可见：Court 保持 LOCKED，展品未被涂绿；书页没有记下的事，不冒充记载。

*model printed from the ledger; not a verdict.*
