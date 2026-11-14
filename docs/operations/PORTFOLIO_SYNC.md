# PORTFOLIO SYNC — 让 xiaodernan.github.io 自动展示最新 SpecProof 成果

> 目标：每次 SpecProof 在 master 上的推进，都自动同步到你的 GitHub portfolio 页面——
> 不是"今天看到一篇静态文章"，而是"点开能看到今天这份修复 / 新模块 / 交付清单的入口"。
> 本文件是这个机制的设计说明书；实际落地需要两个步骤（两个仓库联合）。

---

## 一、同步边界（什么同步、什么不会动）

### 同步的

| 源 | 目标（GitHub Pages 上的静态页面） |
|---|---|
| `CHANGELOG.md` 每段标题 + 概要 | portfolio 侧栏 "SpecProof" 卡片下方的"最新动态"1-liner |
| `docs/operations/DEEP_OPTIMIZATION_PLAN.md` 的最近一条 `## #` 段 | portfolio 的 "最新进展" 模块（日期、提交号、正文头三行） |
| `docs/world/EN/SPECROOF_WORLD_EN.md` 文件大小 + 中文目录 | portfolio "SpecProof 创世记" 链接 + 实时大小 |
| `apps/web/dist` 的 build size 指标 | 作为项目"当前产物大小"展示在 portfolio 上 |
| 本仓库 `master` 的最新 commit hash + `--decorate` | portfolio 页脚 "SpecProof 最新一次提交" 链接 |
| 35 个 page 路由清单（`apps/web/src/pages/`） | portfolio "产品面" 一栏 |

### 不同步的

- **没有任何凭据**： portfolio 不需要看见 .env、.local/llm.json、密钥；
- **没有任何 LLM 调用**： 本同步不消耗 token；
- **没有任何面向访客的 runtime**： 它不是要把 portfolio 搬到服务端跑起来——它是静态的；
- **不需要 docker**： 整个流程是一次 `python scripts/sync_portfolio.py`，写一份 JSON 或 markdown 到 portfolio repo 的 `data/` 目录。

---

## 二、Sync 脚本（可直接用）

`scripts/sync_portfolio.py` 生成以下三份产物：

```json
# .github-sync.json —— 直接可被 portfolio 的静态生成 pipeline 消费
{
  "last_synced": "2026-11-14T15:20:00+08:00",
  "latest_commit": "5f0290b",
  "latest_ledger_entry": {
    "number": 1690,
    "title": "新手手册 · USER_GUIDE.md 落成",
    "date": "2026-11-14",
    "highlights": ["46 路由", "快速路径 5 分钟", "完整手册 7 章"]
  },
  "world_bible_size_bytes": 25404,
  "page_count": 35,
  "e2e_passed_at": "2026-11-13"
}
```

```markdown
# latest.md —— 渲染为 sidebar 的 "上次 ship" 模块
```markdown
## SpecProof · 最近 Ship

**2026-11-14 · 5f0290b** — 新手手册 USER_GUIDE.md 落成

- 46 页应用 · 7 章完整手册 · 中英文双露台  
- 缓存命中率 75-84% (wkapi.pro 实测)  
- 演示 Verify 真机跑通鉴别 AUTH-01  

[→ 看全世界 25.4 KB 的创世记](https://github.com/xiaodernan/specproof)
```
```

```yaml
# 可插入 GitHub Actions workflow（portfolio 仓库里）：
name: sync-from-specproof
on:
  schedule: [{ cron: '0 */6 * * *' }]   # 6 小时一次
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4           # portfolio repo
      - run: |
          curl -sL https://raw.githubusercontent.com/xiaodernan/specproof/master/.github-sync.json > data/specproof-latest.json
      - run: git commit -am "chore: sync specproof latest" && git push
```

### 怎么用

```bash
# 每次 master 跑完对应的 feature 分支 / 每次大步前进后跑一次：
python scripts/sync_portfolio.py
# 把 .github-sync.json 和 latest.md 提到 portfolio repo（自己的 repo）
# portfolio 读 data/ 就更新；无需手动插入。
```

---


## 自动同步（一次配置，长期生效）

本仓库内置了无需人工推送的 GitHub Actions workflow：`.github/workflows/portfolio-sync.yml`。
它在每周日 06:00 UTC、master 合并时、或手动触发时运行，重新生成 `artifacts/portfolio-data/`
并推送 `data/specproof-*` 三件套到 `xiaodernan/xiaodernan.github.io`。

**只需要你配置一次 secret**：

| secret 名 | 用途 | 获取方式 |
|---|---|---|
| `PORTFOLIO_TOKEN` | 推送 `data/specproof-*` 到 portfolio 仓库 | GitHub → Settings → Developer settings → Fine-grained tokens → 选中 xiaodernan.github.io 仓库 → Contents: read and write → 复制 token 粘贴进 specproof 仓库 Secrets |

**没有这个 secret 也能跑**——workflow 会完成数据重建然后打印一条 notice，不推送、不报错。

**为什么是每周而不是每次 push**：标注「有大提升再更新」——portfolio 是门面不是刻度计。
每周一次外送足够；master 合并触发只在周日抢先、合并多数周无害；手动 `workflow_dispatch` 可临时触发。


## 三、为什么用 pull-model 而不是 push-model

- **安全**： SpecProof 不需要知道 portfolio repo 的写权限——"我把我做了什么写进 JSON，portfolio 负责读"；
- **独立**： portfolio 不依赖本仓库的 API 在线——它只读最文件；对 CI 掉线也能继续工作；
- **可选**： portfolio 可以选择显示 / 不显示任何一个字段——"打开 public 页面看到 36 个页面" 是 portfolio 的选择，不是本仓库的决定；
- **审计**： portfolio 的 commit 可以直接看见所有字段全部来自 master 的决定，没有"手工拼凑"。

---

## 四、不承诺的事

- 本同步脚本不会 "自动 push 到 portfolio repo"——
  - 需要 credentials（portfolio 的 write token）——
  - 放在本仓库 = 凭据泄露给 fork；
- portfolio 上传 **一定是手动触发**（或 cron）。本脚本只生成文件。
- 不同步任何操作者/commit R/O 账号（不做 issue 导入）；
- 不同步 SpecCraft agent 任务结果（它属于产品 runtime，不是文档站）。

---

## 五、入口位置

| 文件 | 作用 |
|---|---|
| `scripts/sync_portfolio.py` | 生成 `.github-sync.json` + `latest.md` + `products.json` |
| `docs/operations/PORTFOLIO_SYNC.md` | 本文件——sync 的总体设计和边界 |
| `.github-sync.json` | 脚本输出；可直接 commit 到 portfolio repo |
| `apps/web/dist/*` | build 产物（按需 serv 静态侧） |
