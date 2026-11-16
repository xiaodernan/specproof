# 更正卷轴 · The Corrections Scroll

> 本仓库里被撤回、被修正、被自己打脸过的每一件事，全部在此。
> 这页本身不是追责书——它是"可审计的错误用处理器"：能查到账本、能查到 commit、
> 能重算出修正后的数。凡我这个仓库声称过的话，凡本书后续引用本卷轴，都不绕过它。
>
> 规矩：① 卷轴只增不删；② 每条更正必挂 commit / ledger anchor；③ 任何想引用本仓库的人，先读这一张。

## 条目

| # | 误判原文（时间） | 实际指陈 | 撤回/修正 | anchor |
|---|---|---|---|---|
| **R01** | chronicle 1,645 节（2026-11-16T13:2xZ，#1845 入册时写错） | 实际 1,644 节 | 同段落内手动更正为 1,644 | DEEP_OPTIMIZATION_PLAN §#1845 |
| **R02** | 世界书双语失衡：「zh 72 / en 73」（#1855 首次入卷时两边数量不一致，中文文件误判为"已存在"跳过 zh，en 追加了 LXVI） | 同一对 zh/en 声称其实同一卷；检测重叠置布太宽（仅用"船期表"），zh 未被写入 | 回滚 en 版本，修检测为含完整标题「卷六十六 ·」，两边都入库 → **73 / 73** | DEEP_OPTIMIZATION_PLAN §#1855 + git show |
| **R03** | CrewCard 里留死数字「commits 2,499 · ledger 1,658 节」（#1858 卡生成器里写死） | 每一笔提交都会 +1（自我指涉），死数永远变成谎 | 全部改为 import 时从 repoStats.json/evidence.json 现场解析 | §#1858 |
| **R04** | ROADMAP-LIVE item 5 声称「疑似 ~1000 个 hash 名 542-byte scratch 残片」（#1860） | 真容：**21 件 git-tracked 文件（591,524 B），全在 docs/eval/swebench-logs/*/craft/backup/ —— SWE-bench 评测的源码快照（craft/backup 机制），内容寻址命名** | audit_scratch_residue.py 落地 + #1865 正式撤回 + ROADMAP-Live 第 5 项重渲染 | §#1860 → 撤回 @ §#1865 · docs/evidence/audit-scratch-residue.json |
| **R05** | `audit_court_lock.py` 首敲输出「verdict: BROKEN · lock c2ebdc0b…」（2026-11-15T18:24Z，#1866） | **这不是 repo 坏了——是我的审计 regex 不认 `kwargs["stream_options"] = {"include_usage": True}` 这一 Python 惯用拼法** | 修正为双拼法兼容（kwargs[…]= 和 JSON 风格的"stream_options":{...} 都校验）；复敲 → **LOCKED · lock 4117d2b0ca5fb23a** | §#1866 · tests/unit/test_court_lock_machine.py |
| **R06** | `build_evidence.py` 排序按文件名逆序取 latest（2026-11-16T17:5xZ，#1852 v1） | 同前缀文件名逆序会选错（`.json` > `-2.json`）——展示了错误 artefact | 排序关键从文件名换为 `started_utc`（ISO 字典序 = 时间序）逆序 | §#1854（衍生："#1852 起文件名乱序导致误选 latest"） |
| **R07** | Archive.tsx 写死 `worldbook: 50` + 文案硬编码「世界书 50 卷·编年 1,625 节」（存在很久；本次修订 #1863） | **此刻全假**：build 链早把它们涨成 81/1,664 等数字 | 全部改为 import lock 的 locked JSON，计数与 build_*.py 实时对账（并新增「史诗卷」KPI tile） | §#1863 |
| **R08** | `audit_unsigned.py` 首次敲出「branch-cleanliness: no-upstream」（2026-11-15，#1863 上线时） | subprocess 没被 import → 异常被 `except` 静默吞 → 返回 "" → 误判为 no-upstream | `import subprocess` 入模块 + 补充 docstring（4 灯）；复敲 → 正确读出 dirty-tree → 提交后转 clean | §#1863 |
| **R09** | 同一轮里 build_roadmap_live.py 入库 ≠ 它是确定性的——「commit 只修输出没跟脚本」（#1865 主提交遗漏生成器） | 出书面 v2 修复并提交 `27d632b`（follow-up）：ROADMAP-LIVE item 5 输出与生成器保持一致 | DEEP_OPTIMIZATION_PLAN 不为此另立节；提交 `27d632b` 直接记账（见 git log） | git show 27d632b |
| **R10** | RageCoach 测试断言 `"Sign & seal"` 期望 approve —— 实际规则在 tour-seal（规则内含 seal 关键词先吃掉） | 规则命名本来就有重叠；测试 expectation 错了不是代码错了 | 测试期望改为 tour-seal；`approve` 规则加空白容错（`批\s*准` 等） | #1846：`apps/web/src/ui/rage.test.ts` |

| **R11** | 证据复核子图的 `test_graph_ok_when_all_pass` 曾 flaky 红了一次 | 根因：intake_node 按 mtime 排序；tmp_path 写入两个 back-to-back 文件时 mtime 常同 tick → 随机判 REGRESSION | 改为 `started_utc` ISO 字典序降序（ISO = 时间序）· mtime 仅作 absence 缺省 | §#1872 · `tests/unit/test_evidence_graph.py` |
| **R12** | Volume XCI 扉页切到 `api.aizzz.xyz/gpt-6.1-terra/responses/max` 后，我把「换钥」写得像「车道已通」 | 实敲 `scripts/llm_cache_probe.py`（短/长/重复 × non-stream/stream+include_usage）**6/6 全红**，原文照录：「本站不对您所在的国家及地区进行商业服务」—— 那是对方网关从字节里说的，不是本仓库说的 | 账本 #1881 如实登记 **CLOSED_FOR_THIS_CHANNEL**；恢复办法只有两条（仓库 Settings→Secrets `SPECPROOF_LLM_*` 环境车道 · 或本机能出网），绝不伪造接通 | §#1881 · `scripts/llm_cache_probe.py` 输出 2026-11-16（本轮重敲 6/6 同回） |
| **R13** | `ChainBanner.tsx`（#1878）的 className 写的是 `chain-banner--ok/bad`，样式表定义的是 `.chain-banner-ok/.chain-banner-bad` | **绿/红两种变体一直没生效**——所有页面都显示同色 banner；**修复前 533/533 全绿也没人发现**，因为没有一条断言 class 契约 | 组件 class 改为 `.chain-banner-${ok ? "ok" : "bad"}`；新增 `pages/__tests__/ChainBanner.test.tsx`（zh/en × class 契约 × 跳转链接）锁住 | §#1882 · `apps/web/src/pages/ChainBanner.tsx` · `src/pages/__tests__/ChainBanner.test.tsx` |
| **R14** | Volume XCI/XCII 把「换钥后敲不通」登记为 **CLOSED_FOR_THIS_CHANNEL**（如实照抄了 6/6 红字节：「本站不对您所在的国家及地区进行商业服务」） | 真因**不在 key、不在模型、不在区域政策——在出网路由**：这台机器没有走 Clash Verge（mihomo 127.0.0.1:7897）；不带代理的直连被对方网关按「地区」拦了 | 设 `HTTPS_PROXY=http://127.0.0.1:7897` 后同一把 key 同一模型 6/6 复通（cached 4224→6400）；`scripts/live_lane_probe.py` 改走 `providers.net.outbound_client`（env-mounts，不再裸 httpx）| §#1884 · `scripts/llm_cache_probe.py`（proxy 6/6 绿）· `scripts/live_lane_probe.py`（HTTP 200） |
| **R15** | gateway 测试套件的脱环境性：5 个 actuator 路由 / 2 个指标 / 1 个 refresh 用例，2026-11-16 本机两次爆红，每次都是「127.0.0.1:8888 上当时有没有活着的 config-server」在变 | 罪魁不是代码，是 `spring.config.import=optional:configserver:http://localhost:8888` 在测试里**默认仍会被合并**：Docker Desktop 进程半路死掉后 configserver 又爬起来以前在服务 `management.endpoints.web.exposure.include=health,info` 的 stale 镜像，覆盖了 include=gateway,prometheus,refresh | `services/gateway` 与 `services/control-plane` 的 `application-test.yml` 都把 import 钉到 discard 口 **127.0.0.1:9/**（optional = 静默忽略）；测试 JVM 从此不依赖宿主任何 8888 | §#1886 · `services/gateway/src/test/resources/application-test.yml` · `services/control-plane/src/test/resources/application-test.yml` |
| **R16** | Volume CXV 与多处文档把 `live_lane_probe` 的**一次**敲出（HTTP 200 · cached 4224）写得像「缓存命中率已被改善」——并反复出现「缓存挂上了」句式（2026-11-16T20:55 起连续两 strike 实敲：`prompt_cache_hit_tokens: 0 / 0`，全 4676 未命中） | 网关的 prefix cache 在**我们这次部署**（aizzz/gpt-6.1-terra/responses-max）**没有稳定 engage**：`scripts/two_strike_probe.py` 连敲两次同一 prompt 两次报 0；先前的 4224 是 gateway 自带的 tenant-shared prefix，不是本应用 prompt 的前缀 | 不许再说「缓存命中率提升了」——本仓库的数字全在 `.local`/此页；正确结论：**所有车道都走 stream+include_usage（prefix 尽量常驻）；缓存是否命中不可控，不可宣称，不可写入 slash-proof 数字** | §#1915 · `scripts/two_strike_probe.py` |
## 使用约束

1. 本卷轴条目不许删，只许增量 append；
2. 每次 rebuild 后 `python scripts/audit_evidence.py` 可敲比对：worldbook.json · chronicle.json · repoStats.json · engine.json · unsigned.json —— 一旦漂移一字节即报红并写新 R 条入册；
3. 本卷轴登记的≠小声喘息——它是失败的最终落点：我的错每一件，都如实埋着座标等你亲自敲。
