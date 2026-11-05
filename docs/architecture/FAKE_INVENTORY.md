# 手写假清单：哪些是 SQL 假，哪些不是

> 这份清单是**测出来的**，不是列出来的。生成器：`scripts/classify_test_fakes.py`
> （可重复运行；`--json` 给出机器可读的形式）。
>
> 本页数字对应 `60def7b`（#600 落地的树）。规则或 `tests/` 里的假一变，
> `tests/unit/test_fake_inventory_stays_measured.py` 会先红——数字不能靠手改跟上代码。
>
> **红自己交代原因（#601 起）**：门里钉的不是四个整数，而是一个**提交号** + 那一棵树上的三个数。
> 数目一变，红就把「哪一类进了/出了哪几个类、在第几行」现算出来——
> `git archive` 取钉住的那棵树、用**同一个分类器**再量一次、再对每条入场做 `git blame`。
> 以前这一段是注释里手抄的十条名册（#545），抄一次对一次，改一次就得重写一次；现在它没有可抄的了。
> 归属只有三种答案：**在某个提交里**（印那笔提交的标题）、**在工作树里**（还没提交，git 把该行记成全零
> revision，红就说「未提交」而不是编一个 sha）、**在一个 HEAD 里还没有的文件里**（blame 直接拒答，
> 而拒答本身就是答案：这是新写的活，不是「这里读不到历史」）。

## 为什么要有一份清单

账本里排了很久的一条队列项是「**其余手写假换成求值器**」（#303 队列项④）。
那条**框法不准**——它把「手写假」当成了一类东西。

实测（本仓 `tests/` 下按类名与实现的方法面自动分类）：

| 类别 | 数量 | 含义 | 求值器能替吗 |
|---|---|---|---|
| **SQL 假** | **20** | 实现了 SQL 面（`cursor` / `fetchall` / `fetchone` / `commit` / `rollback` / `executemany` / `query` / `select` / `insert` / `update`；**`execute` 单独出现不算**，见下面「`execute` 撞名」） | **能**——求值器就是替这一面 |
| 仓储鸭子类型 | 44 | 实现的是**领域方法**（`save` / `find_by_id` / `incr` / `expire` / `publish` / `delete` …） | **不能**——换成求值器等于把它变成**真 store**，那是另一类改动 |
| 普通替身 | 205 | 只实现被测代码用到的那几个方法 | 不在讨论范围内 |

⇒ ⇒ **手写假一共 269 个，而「SQL 假」只有 20 个（约 8%，精确 7.4%）** ⇒ ⇒ 原队列项瞄准的集合比看上去小一个数量级 ⇒ ⇒
且那 20 个类分布在 **12 个文件**里（其中 8 处是「一个游标 + 一个连接/存储」的分体，如 `_FakeCursor` / `_FakeConn`）⇒ ⇒ **真正独立的 SQL 替身 12 处**（这一句以前是「约 10–12 处」的**估计**，现在能数了）。

⇒ ⇒ **结论（这条队列项就此重框）**：
1. 「把手写假换成求值器」**不成立**——多数手写假**根本不与 SQL 打交道**（它们替的是领域方法）⇒ ⇒ 换掉它们会让测试**从替身变成真 store**（⇒ 更慢、⇒ 更容易因环境而红、⇒ 且测的是**真 store**而不是被测代码）✗。
2. 真正可以换的只有**12 处 SQL 替身** ⇒ ⇒ 那是**一小块**具体工作（⇒ 下一个号可以做，或干脆不值得做——**判据是「换了以后，测的是不是同一件事」**）。
3. 剩下的 44 处仓储鸭子类型与 205 处普通替身**留在原处**——它们是**恰当的**测试替身（替的是**被测代码依赖的接口**，不是数据库）✓。

## 再收窄一层：哪些 SQL 假**真的**在写规则？

「有 SQL 面」还不够。求值器能替掉的是那种**按 SQL 文本决定答案**的假——它自己成了生产 SQL 的**第二意见**（`fake_sql_engine.py` 的 docstring 记的就是这件事：那种假让测试**在测假自己**）。

`scripts/find_rule_shaped_sql_fakes.py` 按「有没有拿 SQL 文本做决定」再分一次 ⇒ **只有 2 处**：

| 位置 | 它按文本派发的是什么 | 换求值器？ |
|---|---|---|
| `tests/unit/test_audit_action_parity.py::_FakeCursor` | **问题**（`SELECT COUNT(*)`? 存在性探针?）⇒ 按「问的是什么」给答案 | **不换**——被测的是「清理发了哪几条语句」✓，求值器会把「发了什么」变成「算出什么」⇒ **测的东西变了** ✗ |
| `tests/unit/test_web_api.py::FakeCursor` | **问题**（5 个不同的 SELECT ⇒ 各自的罐装答案） | **不换**——被测的是 API 的**回答形状** ✓ |

⇒ ⇒ ⇒ **结论：0 处需要换** ⇒ ⇒ ⇒ 那条队列项（#303 队列项④）**就此关闭** ✓ ⇒ ⇒ 理由不是「懒得换」，而是**换掉会改测的东西** ✓ ⇒ ⇒ 判据写在上面（**派发的是「问题」还是「数据的规则」**）✓。

**顺带确认**：`tests/unit/fake_sql_engine.py`（那个**求值器**）**已经存在** ✓ ⇒ ⇒ 回收器那条用例**早就换过了** ✓ ⇒ ⇒ 「把其余的也换掉」这件事的**剩余部分**本来就很小 ✓（= 0 ✓）。

## `execute` 撞名：#431 的 `DummyAdapter` 不说 SQL

`tests/unit/test_adapter_protocol.py::DummyAdapter`（#431，`a88fbce`）有一个 **classmethod `execute`**——它**跑构建命令**，不跑 SQL 语句。旧判据是「按方法名」，于是它被算成 **SQL 假**：一个**不是**数据库客户端的类，被计进了「求值器能替」的那 20 个里。

这是**上界**方向的一次假阳性——与本清单诚实边界里说的「下界」方向相反：它把可替换集合**说大了**。而那条队列项（#303 队列项④）正是**照这个集合**关掉的 ⇒ 一个不算数的类进了集合，关掉的理由就得重算。

**判据怎么修的（#545）。** `execute` **单独**出现时不算 SQL 面；同一个类**还有**别的 SQL 面方法时，`execute` 才照旧算。理由是**撞名**：`execute` 这个名字在别的协议里也有一份含义（跑命令），而 `cursor` / `fetchall` / `commit` 这些名字没有这种通用性。

**这条规则不是猜的，是量出来的。**

| 树 | 旧判据 | 新判据 |
|---|---|---|
| 钉下本清单数目的那次提交（#374，`462340d`） | 20 / 43 / 192（共 255） | **20 / 43 / 192（共 255）——一位不改** |
| `origin/master`（#544，`de746b6`） | 21 / 43 / 201（共 265） | **20 / 43 / 202（共 265）** |

⇒ **新判据不改写历史**：在旧树上它给出**一模一样的**三个数；它在当前树上唯一挪动的那个类，是 `DummyAdapter`。

而**总数** 255 → 265 的十个来源是各自可查的提交（`git blame` 在类定义行上取的）：

| 提交 | 类 | 位置 | 新判据下 |
|---|---|---|---|
| #431 `a88fbce` | `DummyAdapter` | `tests/unit/test_adapter_protocol.py` | 普通替身（旧判据算 SQL；`execute` 跑构建命令） |
| #378 `9ac5e9a` | `_FakeGraph` | `tests/unit/test_eval_resume_reuses_measured_cases.py` | 普通替身 |
| #448 `b5e2417` | `FakeStore` | `tests/unit/test_job_stage_declared_edges.py` | 普通替身 |
| #500 `7a7b66b` | `_FakeStore` | `tests/unit/test_dashboard_window_contract.py` | 普通替身 |
| #505 `0dad2d2` | `_FakeGraph` / `_RefusingStore` / `_AcceptingStore` | `tests/unit/test_verify_persistence_failures_are_visible.py` | 普通替身（3 个） |
| #511 `9cfb458` | `_FakeGraph` | `tests/unit/test_verify_contract_list_shows_the_matrix_result.py` | 普通替身 |
| #523 `3494441` | `_Store` | `tests/unit/test_rerank_degradation_cause_is_attributed_and_observable.py` | 普通替身 |
| #524 `74f94d8` | `_Store` | `tests/unit/test_vector_channel_degradation_cause_is_attributed_and_observable.py` | 普通替身 |

⇒ ⇒ 上面这张表是 **#545 当年手抄的一次性快照**——它记的是「旧判据 vs 新判据」那棵树上的差，不是本页表头的当前数字。
**这类名册以后不用再手抄（#601）**：`--explain-drift <钉住的提交>` 会把入场、离场、换桶三类变动连同各自的 `git blame` 归属一起现算出来；门在红的时候直接印它。于是本页剩下的当前数字只有一条来源——分类器自己。

⇒ ⇒ 这十个类**在 #374 都不存在**：所以增量是**十个新类**，不是旧类改了形状。旧判据下它们是 **1 个 SQL + 9 个普通**（21 / 43 / 201）；新判据把那 1 个挪成普通 ⇒ **20 / 43 / 202**。⇒ **「SQL 假 20 个」「需要换 0 处」这两个结论都没有变**；变的是**普通替身** 192 → 202 与**总数** 255 → 265。

## 怎么自己复核

```bash
python scripts/classify_test_fakes.py            # 人读的（按「哪一面」分类）
python scripts/classify_test_fakes.py --json     # 机器读的
python scripts/find_rule_shaped_sql_fakes.py     # 再收窄：哪些按 SQL 文本做决定
python scripts/classify_test_fakes.py --explain-drift 60def7b   # 数目为什么变了（红路径上也会自动印）
```

分类判据（脚本里写死，且**可改**）：
- **SQL 面**：`execute` `executemany` `fetchone` `fetchall` `fetchmany` `cursor` `commit` `rollback` `query` `select` `insert` `update`
  - **例外（#545 起）**：一个类**只有** `execute` 时**不算** SQL 面（撞名，见上一节）。别的面（`cursor` / `fetch*` / `commit` / `rollback` …）**各自单算**——只提供 `cursor` 的假连接仍然是 SQL 假。
- **仓储面**：`save` `save_and_flush` `find*` `get` `set` `delete` `update` `list` `iter` `scan` `publish` `xadd` `lpush` `rpush` `incr` `expire` `enqueue` `dequeue` `claim` `ack` `nack` `heartbeat` `renew` `put` `fetch`

一个类**先**看有没有 SQL 面（⇒ SQL 假），**再**看有没有仓储面（⇒ 仓储鸭子类型），**都没有** ⇒ 普通替身。

## 诚实的边界

- 分类是**按方法名**做的（⇒ 一个用别的名字实现 SQL 的类会被归到别处 ⇒ ⇒ 名单是**下界**不是上界 ✓）。
- **`execute` 这一格是撞名的**（#545 起按上面那条例外处理）：一个**只**提供 `execute` 的类归到普通替身 ⇒ ⇒ 这是往「下界」的方向收紧（更少被算成 SQL 假）✓，但它**不是**证明那个类真的不说 SQL——只是它没有拿出别的 SQL 面来。⇒ 若某个类只提供 `execute` 而**确实**跑 SQL，它会被**漏**掉 ⇒ ⇒ 这是已知的**下界缺口**，不是完美分类。
- 类名是启发式（`Fake*` / `Stub*` / `*Store` / `*Db` / 含 `fake`）⇒ ⇒ **没被名字命中的替身不进名单**（⇒ 名单也是下界 ✓）。
- 本页的**当前数字**由门每轮重测 ⇒ ⇒ 它一旦与代码不符，门先红，并且**红里带着「哪几个类造成的」**（⇒ ⇒ 前提是钉住的那个提交在本次历史里可达；不可达时另一条腿先红，不会给出一个读不出来的解释）✓。
- 本清单**只做分类** ⇒ ⇒ **没有换任何一处替身** ⇒ ⇒ 「换不换」的**结论**已给出，**动作**没做。
