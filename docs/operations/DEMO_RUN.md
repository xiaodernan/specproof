# 演示 · `specproof demo --run` 完整走一遍

> 目的：被记录一次，不是展示。每次上机后你可以直接复用，不必从头推断。
> 读者：新的贡献者 / 面试官 / 隔壁来看一眼的同事。

## 什么时候读这个

当你看到以下情况之一，你需要它：

- 当你刚 clone 项目、想在本地看到 SpecProof 真刀真枪跑；
- 当你准备把这个仓库演示给别人、不想依赖网络或外部 LLM；
- 当你想回归验证差分运行器在新改动之后还能抓住 `head-v1` 那一处注入的缺陷；
- 当你在 FAR / NEAR 环境下想确认 `spring-backend` 工程没被动过手脚。

## 你需要什么

| 项 | 最小 |
|---|---|
| Java | 17+（demo 的 spring-boot 工程瞄准 17） |
| Maven | 3.9+（已 `mvn package` 成功，`target/demo-backend-1.0.0.jar`） |
| Python | 3.12（本机实测过，使用 `.venv`） |
| 内存 | ≥ 1.5GB 空闲（FAST 模式不跑 Docker；Gradle/JVM 会爬上 ~600-800MB） |
| 磁盘 | ~1.1GB Maven 缓存 + ~80MB 构建产物 |

## 一次完整跑通

```bash
# 1. 确保演示仓库准备好（幂等）
specproof demo           # 看 demo 准备状态，不跑验证
# 预期输出：
#   ==> 准备演示仓库 (demo/spring-backend) ...
#       [..] git 历史已存在 (base / head-v1), 直接使用

# 2. 跑验证（FAST 模式，确定性，不用 LLM，可离线）
specproof verify \
  --repo demo/spring-backend \
  --base base --head head-v1 \
  --spec demo/requirement.txt \
  --depth FAST \
  --output-dir ./reports \
  --no-llm

# 预期：
#   Verdict: BLOCKED
#   Blocked finding: AUTH-01 — changeEmail 权限注解被移除（base_pass_head_fail）
#   Artifacts: reports/verification-report-<timestamp>.html + capsules/capsule-<id>.zip
```

## 内部状态

`demo/spring-backend` 有两个 tag：

| tag | 内容 |
|---|---|
| `base` | 原始 Spring 实现——`changeEmail` 有 `@PreAuthorize("isAuthenticated()")` |
| `head-v1` | 注入缺陷：移除 `@PreAuthorize`——差分必须可抓到此 |

两个 tag 都指向真正的 Spring Boot 工程；`.mvn/` 也在仓库里。**不需要联网下载 Maven 依赖**——
本机已有 `~/.m2/repository` 缓存（约 1.1GB），Java 17 + `mvn package` 离线通过。

## 什么会查、什么不会查

| 深度 | 这个 demo 会做什么 | 这个 demo 不会做什么 |
|---|---|---|
| FAST | 差分执行本地 JVM / 编译 Java / 生成反例 | 不调用 wkapi.pro / GPT 6 sol；不跑 Docker；不跑 RabbitMQ 验收 |
| FULL | 额外 call LLM 给架构评审 + 运行时证据分析 | 同样需要网络；`@全量` 对这里没有特殊含义 |

`FAST` 很便宜——它把验证的速度计费模型简化成了 **"看到缺陷需要多少个编译周期"**。
`FULL` 是一个面向恶意/模糊变更的超级武器，通常留给 CI 答复 PR 做一次性签字判断。

## 失败情况与处置

| 症状 | 大概率原因 | 怎么办 |
|---|---|---|
| `git` 指令报错 | `demo/spring-backend` 不是 git 仓库（被裁剪） | 删 `demo/spring-backend/.git/` 然后重跑 `specproof demo` 重建 tag |
| Maven 下载报错 | 离线缓存空了 | 跑一次在线 `mvn package` 先填满 ~/.m2，然后从这再来 |
| `Report not found` | output-dir 为空但 `--output-dir` 指向了新文件夹 | 指向 `reports/`，或把 `reports/` 建出来 |
| 找不到 .venv | Python 环境没激活 | 用 `python -m cli.specproof.main` 而不是 `specproof` |

## 复现提示

为了让每次上机都能看到一样的缺陷：

```bash
# 确认 tag 指向同一 commit
cd demo/spring-backend && git rev-parse base head-v1
# 预期：
#   3194fb6a129ab11de1899cc071512ce800e2a727  (base)
#   c13d122ebed0d4ec2419238d8c8ebeddab0c6a36  (head-v1)
```

两个 commit hash 固定后，演示在每个新 clone 的机器上都能复现。
