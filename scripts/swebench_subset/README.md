# scripts/swebench_subset — 精选 Python 子集 (LLM 模式)

`python_subset.json` 是一个 `instance_id` 数组 (SWE-bench-Lite test split,
共 10 个), 给 `scripts/bench_swebench.py --mode llm --instances-file` 使用:

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
python scripts/bench_swebench.py --mode llm \
    --dataset princeton-nlp/SWE-bench_Lite \
    --instances-file scripts/swebench_subset/python_subset.json \
    --repo-dir D:\swebench-repos --output docs/eval/swebench-results.json
```

## 选取标准 (selection criteria)

从 300 例 test split 里筛出 10 例, 每一条都满足:

1. **纯 Python 仓库、小体量**: flask / pylint / sphinx, 无编译型依赖;
2. **pip 依赖平凡**: `pip install .` 即可 (纯 wheel, 全部是纯 Python 依赖树),
   不需要系统库、不需要数据库/容器;
3. **FAIL_TO_PASS 是纯单元测试**: 不碰网络 (无 httpbin/live server)、不碰 DB、
   不碰 Docker — 本地 plain pytest 可直接重放;
4. **PASS_TO_PASS 列表短** (≤ 54 条): 每节点一次 pytest 子进程, 短列表保证
   判定阶段可快速重放;
5. **避开重依赖仓库**: astropy / matplotlib / scikit-learn / pandas / xarray /
   seaborn / django (及其它 C 扩展或系统依赖实例) 全部排除。

组成: pallets/flask × 3, pylint-dev/pylint × 4, sphinx-doc/sphinx × 3。

## 诚实限制

- 依赖安装按"首个匹配的安装配置"执行 (pyproject.toml → setup.py →
  setup.cfg → requirements.txt, `pip install .` 或 `pip install -r`);
  新版依赖漂移 (如 werkzeug 3.x vs flask 2.3) 可能导致失败 — harness 会
  诚实记录 `unresolved (deps unavailable)` 或测试失败, 绝不掩盖。
- 共享 venv: 每次运行所有实例共用一个 venv (非官方逐实例 Docker 环境),
  见 docs/eval/SWEBENCH_PLAN.md。
- 此子集是 harness 口径的自测子集; 官方 300 例全量口径仍需逐实例 Docker
  镜像 + 官方 log-parser, 是文档化的人工步骤。
