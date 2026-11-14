# 巡览玩法手册 · The Grand Tour — How to Play

> 「巡览」是 SpecProof 里唯一一件像游戏的东西：你走进一个陌生产品，必须自己动手把六件事做完，
> 每做完一件盖一枚章；六章盖齐，红印落下。
> 本手册把玩法、路线、机关、结局和彩蛋讲清楚——**照着做就能通关**。

---

## 一、这是什么

一次"验收官入职训练"。

玩家扮演一名新上任的验收官（Acceptance Officer）。六卷场景把 SpecProof 最要紧的六件事各演一遍：
连接工作区、读验收报告、读矩阵、读发现、读史册、盖印归档。

- **没有分数**。进度条只数"你亲手做了几件事"；
- **没有计时**。你可以在第 2 卷坐一晚上；
- **没有假进度**。每一卷的"盖上此卷"只有你自己按下去才会算数——系统不替你判定；
- **状态在你本机**（`specproof_tour_v1`，localStorage）。换浏览器 = 重新入职。这不是 bug，这是这产品的脾气：信任要自己从零捡起来。

## 二、怎么开始（三步）

1. 打开产品，左侧栏点 **巡览**（Grand Tour）；
2. 读卷首的**序**（它会告诉你这趟旅的意义）；
3. 从**卷一 · 门**开始，按钮叫「盖上此卷」。

## 三、六卷路线（照着做可通关）

### 卷一 · 门 · THE GATE
**目标**：连接工作区。
- 点卷一的「前往登录 →」→ 用访问令牌（`sp_*`）登录 → 回到巡览页 → 「盖上此卷」。
- **授意**：令牌只存在本浏览器 sessionStorage，不上传、不共享。别人给不了你令牌，你也不必给别人。

### 卷二 · 验 · THE VERDICT
**目标**：读一份真的验收报告。
- 点「前往变更验收列表 →」→ 打开任意一条作业 → 在「验证概览」页把四张卡片读一遍：
  验证结论 / 验收条件 / 未通过 / 未验证；
- 回到巡览 → 「盖上此卷」。
- **授意**：点开「执行进度」页签看阶段时间线——那里没有一个时间戳是编的。

### 卷三 · 山 · THE MATRIX
**目标**：站到矩阵前，问一句"这是铁证还是纸"。
- 点「前往矩阵 →」→ 找一行 `base_pass_head_fail`（改前通过、改后失败）；
- 读它的「证据方式」中文释义，再点开该行的 findings 细节；
- 回巡览 → 「盖上此卷」。
- **授意**：如果一行写的是 `static_analysis`，它**不是**铁证——是"可能对"。承认这一点，你就懂了一半。

### 卷四 · 府 · THE DISCOVERY
**目标**：读一条 finding 的门道。
- 打开任意作业 → 「风险发现」页签 → 点开一条：severity 是 BLOCKER 吗？evidence_type 读出来像铁还是像纸？
- 顺手点一次「复制 Markdown 摘要」，粘贴到任何地方——这就是评审官读证据的方式；
- 回巡览 → 「盖上此卷」。

### 卷五 · 史 · THE CHRONICLER
**目标**：读史册，并验证它。
- 点「前往史诗页 →」→ 读任意一卷 → 找到「史官细则」里的**提交号**；
- 在终端跑 `git log --oneline | grep <那个号>`——**能查到，这一卷就是真的**；
- 回巡览 → 「盖上此卷」。

### 卷六 · 印 · THE SEAL
**目标**：盖章。
- 在任意验收页点「复制史诗纪要」→ 粘贴给自己；
- 回巡览 → 「盖上此卷」→ 进度条满 → 红印「验讫」落下 → 出现那句话：
  **「六卷齐盖，章落。」**
- 到此通关。

## 四、机关与彩蛋

| 机关 | 触发 | 你会看到 |
|---|---|---|
| 反悔 | 任意一卷点「撕掉此卷（反悔）」 | 该卷印章消失、进度条回退、**通关印被收回**（卷六被撕时） |
| 清零 | 页面底部「重新巡览（擦除本机印记）」 | 全部六枚清空、进度条归零 |
| 损坏检测 | 手动改坏 localStorage 里的 `specproof_tour_v1` | 页面顶部如实说"本机巡览进度读不出来"，并按全新状态呈现——**不假装你走过** |
| 不可保存 | 无痕模式 / 策略禁用 localStorage | 页面顶部说"盖下的印刻不进去了"，并明确"完成不会在刷新后保留" |
| 真验 | 终端 `git log` 查到卷五的提交号 | 你手里就有了验证史官的手段——这才是巡览真正想给你的东西 |
| 英文卷 | 顶栏语言钮切到 `EN` | 同一套六卷，全英文——**不中英夹杂**（有 parity 门守着） |

## 五、常见问题

**Q：盖了章，刷新后没了？**
A：进度存在本机 localStorage。若刷新后真的没了，说明该 profile 的存储被禁用了——页面会在你盖的那一刻就提示过。若你换过浏览器/窗口（无痕），进度本来就不跟着走。

**Q：一定要按那个按钮吗？**
A：是。巡览不读 API 判定"你大概看过了"，它只记你按过。这与 SpecProof 的整个哲学一致：**证据要具体到一次操作，不接受推测**。

**Q：巡览算不算"验收"？**
A：不算。巡览只是入职训练——真正的验收是 `specproof verify`：差分执行、矩阵列罪、红章盖在报告上。巡览的章盖的是"我懂了"，不是"代码没问题"。

**Q：能给别人看我的进度吗？**
A：不能，也不该。进度在本机。

---

# The Grand Tour — How to Play (English)

> The Grand Tour is the one thing in SpecProof that plays like a game: you walk into an unfamiliar
> product and must complete six things by hand, stamping each one. Six stamps and the red seal falls.
> This manual explains the rules, the route, the mechanisms and the ending — **follow it and you win**.

## 1. What it is

An acceptance officer's first night. Six scenes stage the six things that matter in SpecProof:
connect the workspace, read a verdict, read the matrix, read a finding, read the chronicles, seal the file.

- **No score.** The progress bar only counts what you personally did.
- **No timer.** You may sit with Volume 2 all night.
- **No fake progress.** A station counts only when *you* press the seal — the system never guesses.
- **State lives on your machine** (`specproof_tour_v1`, localStorage). A new browser means a new first night.
  That is not a defect; it is this product's temperament: trust must be picked up from zero.

## 2. How to start (three steps)

1. Open the product, click **巡览 / Grand Tour** in the sidebar;
2. Read the prologue;
3. Start at **Station I · The Gate** and press 「盖上此卷 / Seal this station」.

## 3. The route (six stations, follow and you finish)

| Station | Do this | Then |
|---|---|---|
| I · The Gate | Sign in with your access token (`sp_*`) | Seal it |
| II · The Verdict | Open any verification and read the four cards (verdict / contracts / failed / unverified) | Seal it |
| III · The Matrix | Find a `base_pass_head_fail` row, read its evidence type in plain words | Seal it |
| IV · The Discovery | Open one finding; is the severity a BLOCKER? Copy a Markdown digest | Seal it |
| V · The Chronicler | Read any scroll and find its commit hash — then `git log` it | Seal it |
| VI · The Seal | Copy an Epic Certificate to yourself | Seal it → the bar fills, the red 「验讫 / SEALED」 stamp falls |

## 4. Mechanisms

| Mechanism | What happens |
|---|---|
| Change your mind | "Unseal" any station — its stamp disappears, the bar retreats, and a completed seal is revoked |
| Start over | "Restart the tour" wipes all six stamps |
| Corrupted record | Hand-edit localStorage → the page says it cannot read the progress and shows a fresh start — it never pretends you walked it |
| Storage disabled | The page says the seal did not stick, and that "done" will not survive a reload |
| Real verification | `git log` the hash from Station V — now you hold the chronicler's own instrument |
| English edition | The language toggle turns the same six stations fully English — no mixed screen (a parity gate guards it) |

## 5. Honest limits

The tour is onboarding, not verification. Real verification is `specproof verify`: differential
execution, a matrix of charges, a seal on a report. The tour's stamp means *"I understand"* — never
*"the code is fine"*. Progress never leaves your machine.
