# 威胁测试: 恶意构建脚本 / 输出洪水 / 缓存投毒 (backlog #7)

三类离线攻击测试, 证明或修复沙箱对三类威胁的防御。全部测试无 Docker、
无网络、无真实密钥; 恶意载荷只在 tmp 目录/argv 中作为惰性字符串存在。

## 1. 恶意构建脚本 (tests/fault/test_malicious_build.py)

威胁: 恶意 PR 的构建命令试图改写工作区外文件 / 删除关键文件 / 覆盖 mvnw。

| 防御层 | 断言方式 | 结果 |
|---|---|---|
| Executor 命令白名单 (craft/executor.py) | 非白名单脚本 stem (sh/bash/cmd/powershell/mvnw/…) 在执行前抛 CommandNotAllowedError, 假 runner 证明零到达 | 已满足 (测试证明) |
| Docker 挂载布局 (sandbox/runner.py) | 工作区 :ro 挂载 + 仅 target/ 可写子挂载; mvnw 不单独挂载; 无工作区下其他可写宿主路径 | 已满足 (测试证明) |
| 提权/外传通道 | --user 1000:1000 / --cap-drop ALL / no-new-privileges / --network none / 无 docker.sock | 已满足 (测试证明) |
| docker 模式绝不落回无沙箱执行 | daemon 不可用时硬错误, local_command 标记证明零执行 | 已满足 (测试证明) |
| auto 落回必须留痕 | 落回结果 mode=local_fallback 且 error 保留 docker 失败原因 (**修复**: 原实现丢弃失败原因) | 已修复 |
| **钉住的缺口**: 显式 local 模式无隔离 | 真实 tmp 运行证明白名单解释器可覆盖 mvnw / 写工作区外 / 删关键文件 | 缺口钉住 (注释) |

缓解事实: 生产 compose.production.yml 钉死 SPECPROOF_SANDBOX=docker
(测试断言)。后续硬化 (拒绝为不可信内容使用 local 模式) 落地时, 需翻转
TestLocalModeTamperingGapPinned 三个用例为断言拒绝。

## 2. 输出洪水 (tests/fault/test_output_flood.py)

威胁: 构建/测试输出数百 MB, 试图 OOM worker 或淹没证据。

防御 (sandbox/runner.py): bound_output 将保留输出限定为
**头部 + 显式截断标记 + 尾部**, 中段丢弃; SandboxResult 新增
truncated / truncated_chars 字段诚实上报。下游 (executor、工具层、
证据写入) 从此不再持有完整洪水。

- 预算: SPECPROOF_SANDBOX_OUTPUT_HEAD / SPECPROOF_SANDBOX_OUTPUT_TAIL
  (默认各 32768 字符); 标记格式:
  `[... sandbox output truncated: N chars omitted ...]`
- 测试内存控制: 洪水大小由 SPECPROOF_FAULT_FLOOD_BYTES 配置 (门禁默认
  2 MiB); 子进程按 4 KiB 分块写出 (子进程内存恒定), 测试自身不物化
  完整洪水。
- **实测**: SPECPROOF_FAULT_FLOOD_BYTES=268435456 (stdout 256 MiB +
  stderr 128 MiB = 384 MiB 总洪水) 9/9 用例通过, 用时 11.06 s, 无 OOM,
  保留量与预算完全一致。
- **钉住的缺口 (捕获)**: runner 仍以 subprocess.run(capture_output=True)
  先缓冲完整输出再做保留截断, 进程峰值内存随洪水大小线性增长。保留
  RETENTION 已受界 (本测试证明), 峰值 CAPTURE 受界需流式读取, 为后续项。

## 3. 缓存投毒 (tests/fault/test_cache_poisoning.py)

威胁: 依赖缓存 (MAVEN_USER_HOME / venv) 被投毒后, 下一步执行静默使用
投毒产物 — 对验证管线自身的供应链攻击。

防御 (新增 sandbox/cache_verify.py + sandbox/runner.py 接线):
- 种子时生成摘要清单 (JSON: {rel_path: sha256-hex}), 每次执行前逐条
  校验: 摘要不符 / 版本元数据被篡改 / 条目缺失 / 条目超大 (不哈希,
  防 OOM) 均为不匹配。
- 策略 fail-closed: on_poison=fail (默认) → 拒绝执行 (exit -1,
  error 显式说明, 假 runner 证明零次执行); on_poison=rebuild →
  删除投毒条目后继续 (再播种需宿主侧种子步骤 — 沙箱 --network none)。
- 清单缺失/非法/路径逃逸 → 一律 fail-closed, 绝不"跳过校验"。
- run_sandboxed 新增 keyword-only 参数 cache_dir / cache_manifest /
  on_poison (默认不传 = 原行为不变)。
- **钉住的缺口 (docker 命名卷)**: runner 无法从宿主读取 docker 命名卷
  (specproof-maven-cache-1000), 故执行前校验覆盖宿主可达缓存目录
  (local/开发模式、宿主播种缓存); 容器内卷校验需沙箱内检查步骤
  (后续项)。生产接线: 播种脚本生成清单 + worker 传入 run_sandboxed。

## 4. 变更文件 (backlog #7)

- tests/fault/test_malicious_build.py (新, 15 用例)
- tests/fault/test_output_flood.py (新, 9 用例)
- tests/fault/test_cache_poisoning.py (新, 21 用例)
- sandbox/cache_verify.py (新模块)
- sandbox/runner.py (修复: 输出保留受界 + 落回原因留痕 + 缓存校验接线)

## 5. 门禁

```
python -m ruff check <变更文件>
python -m mypy --strict sandbox/runner.py sandbox/cache_verify.py
python -m pytest tests/fault/ tests/unit/test_sandbox_runner.py tests/security/test_threat_vectors.py -q
```

结果: ruff 全绿; mypy strict 无问题; 124 passed, 2 skipped
(Windows 符号链接用例跳过)。
