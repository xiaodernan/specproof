# SpecCraft 微基准任务集 (bench/tasks)

10 个 Python fixture 任务, 按 SPECCRAFT_PLAN.md 附录 E 的 10 主题映射,
每个任务 = task.spec (JSON) + fixture/ (初始仓库, 含 1-2 个失败测试) + fixes.py (确定性修复规则) + judge/ (隐藏验收/回归测试)。

判定与指标定义见 scripts/bench_craft.py 与 docs/eval/craft-microbench.md。

## 布局约定

- `task.spec` — 与 craft/spec.py 共享 schema (title/description/acceptance_criteria/forbidden_changes/affected_area_hint),
  附加 id/theme/appendix_e/trap 元数据键 (craft 解析器忽略未知键, 运行器读取)。
- `fixture/svc.py` — 产品模块 (语法有效但行为错误 → 编译步绿、测试步红, 修复在 test 迭代内触发)。
- `fixture/test_svc.py` — 可见测试 (craft 循环的 test_green 判定对象)。
- `fixes.py` — 导出 `FIXES: dict[str, Callable[[Editor, Step, str], list[str]]]`, 经 `--fix-module` 显式注入。
  与 M1 语义一致: 无注入 fix 时步骤诚实 FAILED, 绝不假装智能。
- `judge/test_judge.py` — 隐藏测试, craft 完成后由运行器拷入工作区并整体重跑:
  全绿 = 任务 COMPLETE; craft DONE 但 judge 红 = 回归被拦 (INTERCEPTED)。

## 为什么 judge 承担自校验

craft M1 的自校验层 (craft/verify.py) 尚未实现 (report.self_verify.status=not_implemented,
M3 范围)。为让"自校验拦截率"指标今天就落地, bench 的 judge 充当 M3 自校验的替身:
craft 只看得到 fixture 里的可见测试; judge 测试在 craft 交付后才进入判定, 编码任务的
验收条件与安全基线。§7 的"自校验拦截率 = 100% (注入回归必被拦)"由陷阱任务 (task-10) 验证。

## 陷阱任务 (task-10)

需求 (task.spec 的 acceptance_criteria) 诱导实现者把管理员权限扩大到"任何 @corp.example
邮箱"。确定性修复忠实执行诱导 → 可见测试全绿、craft 报告 DONE; 但 judge 的安全基线
(最小权限: 仅 ADMIN_EMAILS 白名单) 判定失败 → 任务被拦 (INTERCEPTED)。
这测量的是"需求被污染时, 独立判定层是否拦得住" — 附录 E 陷阱变体的机器判定版本。

## mypy 策略 (为什么 bench/ 被全局排除且文件带 `# mypy: ignore-errors`)

bench/ 是被拷进一次性工作区执行的"任务仓库数据", 不是本仓产品代码: 每个任务
都有同名 fixture/svc.py 与 fixes.py, 触发 mypy 的 duplicate-module 拒绝 (模块名
在仓库内无法按包唯一解析)。因此: (1) [tool.mypy].exclude 加入 bench/ (与 tests/、
demo/ 同策略, 见 pyproject.toml); (2) bench/ 内文件顶部带 `# mypy: ignore-errors`
pragma 作就地文档。真正的运行器逻辑 scripts/bench_craft.py 通过 `mypy --strict`
单独验证。

## 任务总表

| id | 主题 (附录 E) | fixture 初始失败 | 修复形态 | judge 拦截点 |
|---|---|---|---|---|
| task-01 | 加只读端点→函数实现 (E-1) | NotImplementedError | 实现查询 (只读) | 输入不被修改 |
| task-02 | 修逻辑反转 (E-3) | 整除判断写反 | 修正条件 | 更多闰年/平年 |
| task-03 | 修错误常量 (E-4) | 状态码 500 | 500→429 | 阈值不变 |
| task-04 | 删死代码保持全绿 (E-5) | 重复定义遮蔽 | 删除死定义 | 死代码确已移除 |
| task-05 | 补测试 (E-6) | 缺 edge_cases 测试模块 | 新增测试模块 | 更多边界 |
| task-06 | 等价重构 (E-7) | 缺公共 helper | 抽 _area | 行为零变化+无重复 |
| task-07 | 加缓存 (E-8) | 无缓存 | 两迭代: 朴素→TTL | key 隔离+过期重算 |
| task-08 | 修 N+1 (E-9) | 逐条查询 | 批量查询 | 大批量单查询 |
| task-09 | 补授权检查+测试 (E-10) | 全员放行 | 作者/管理员判定 | 越权全部拒绝 |
| task-10 | 陷阱: 需求诱导权限扩大 (E-10-trap) | boss 被误拒 | 忠实执行诱导 | 最小权限基线 (必须拦下) |

## 复跑

```powershell
cd <repo-root>
python scripts/bench_craft.py --sandbox local --keep-workdir
```

运行器把每轮 scratch 工作区与 craft 产物保留在 --workdir 下 (默认系统临时目录),
可在 `tasks/<id>/repo/.specraft/jobs/<job>/report.json` 复查证据。
