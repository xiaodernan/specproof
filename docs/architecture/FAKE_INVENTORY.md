# 手写假清单：哪些是 SQL 假，哪些不是

> 这份清单是**测出来的**，不是列出来的。生成器：`scripts/classify_test_fakes.py`
> （可重复运行；`--json` 给出机器可读的形式）。

## 为什么要有一份清单

账本里排了很久的一条队列项是「**其余手写假换成求值器**」（#303 队列项④）。
那条**框法不准**——它把「手写假」当成了一类东西。

实测（本仓 `tests/` 下按类名与实现的方法面自动分类）：

| 类别 | 数量 | 含义 | 求值器能替吗 |
|---|---|---|---|
| **SQL 假** | **20** | 实现了 SQL 面（`execute` / `fetchall` / `fetchone` / `cursor` / `commit` / `rollback`） | **能**——求值器就是替这一面 |
| 仓储鸭子类型 | 42 | 实现的是**领域方法**（`save` / `find_by_id` / `incr` / `expire` / `publish` / `delete` …） | **不能**——换成求值器等于把它变成**真 store**，那是另一类改动 |
| 普通替身 | 190 | 只实现被测代码用到的那几个方法 | 不在讨论范围内 |

⇒ ⇒ **手写假一共 252 个，而「SQL 假」只有 20 个（8%）** ⇒ ⇒ 原队列项瞄准的集合比看上去小一个数量级 ⇒ ⇒
且那 20 个里有几对是「游标 + 连接」的分体（`_FakeCursor` / `_FakeConn`）⇒ ⇒ **真正独立的 SQL 替身约 10–12 处**。

⇒ ⇒ **结论（这条队列项就此重框）**：
1. 「把手写假换成求值器」**不成立**——多数手写假**根本不与 SQL 打交道**（它们替的是领域方法）⇒ ⇒ 换掉它们会让测试**从替身变成真 store**（⇒ 更慢、⇒ 更容易因环境而红、⇒ 且测的是**真 store**而不是被测代码）✗。
2. 真正可以换的只有**约 10–12 处 SQL 替身** ⇒ ⇒ 那是**一小块**具体工作（⇒ 下一个号可以做，或干脆不值得做——**判据是「换了以后，测的是不是同一件事」**）。
3. 剩下的 42 处仓储鸭子类型与 190 处普通替身**留在原处**——它们是**恰当的**测试替身（替的是**被测代码依赖的接口**，不是数据库）✓。

## 怎么自己复核

```bash
python scripts/classify_test_fakes.py            # 人读的
python scripts/classify_test_fakes.py --json     # 机器读的
```

分类判据（脚本里写死，且**可改**）：
- **SQL 面**：`execute` `executemany` `fetchone` `fetchall` `fetchmany` `cursor` `commit` `rollback` `query` `select` `insert` `update`
- **仓储面**：`save` `save_and_flush` `find*` `get` `set` `delete` `update` `list` `iter` `scan` `publish` `xadd` `lpush` `rpush` `incr` `expire` `enqueue` `dequeue` `claim` `ack` `nack` `heartbeat` `renew` `put` `fetch`

一个类**先**看有没有 SQL 面（⇒ SQL 假），**再**看有没有仓储面（⇒ 仓储鸭子类型），**都没有** ⇒ 普通替身。

## 诚实的边界

- 分类是**按方法名**做的（⇒ 一个用别的名字实现 SQL 的类会被归到别处 ⇒ ⇒ 名单是**下界**不是上界 ✓）。
- 类名是启发式（`Fake*` / `Stub*` / `*Store` / `*Db` / 含 `fake`）⇒ ⇒ **没被名字命中的替身不进名单**（⇒ 名单也是下界 ✓）。
- 本清单**只做分类** ⇒ ⇒ **没有换任何一处替身** ⇒ ⇒ 「换不换」的**结论**已给出，**动作**没做。
