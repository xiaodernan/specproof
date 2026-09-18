"""SpecProof CLI — main entry point.

Commands:
    specproof quickstart  print the zero-config first-run guide
    specproof demo       zero-config tour: prepare the demo repo and run a real verification
    specproof probe      Run LLM provider capability probe
    specproof craft      SpecCraft autonomous coding agent (M1 deterministic)
    specproof verify     Run a verification job
    specproof replay     Replay a bug capsule
    specproof eval       Run evaluation across golden cases
"""

import sys
from pathlib import Path

import click

# Ensure the project root is on sys.path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from cli.specproof.commands.baseline import baseline_cmd  # noqa: E402
from cli.specproof.commands.contract import contract_cmd  # noqa: E402
from cli.specproof.commands.craft import craft_cmd  # noqa: E402
from cli.specproof.commands.demo import demo  # noqa: E402
from cli.specproof.commands.devtools import devtools_cmd  # noqa: E402
from cli.specproof.commands.eval import eval_cmd  # noqa: E402
from cli.specproof.commands.fix import approve_cmd, fix_cmd  # noqa: E402
from cli.specproof.commands.mcp import mcp_cmd  # noqa: E402
from cli.specproof.commands.probe import probe  # noqa: E402
from cli.specproof.commands.quickstart import quickstart  # noqa: E402
from cli.specproof.commands.replay import replay  # noqa: E402
from cli.specproof.commands.verify import verify  # noqa: E402

HELP_EPILOG = """\b
第一次使用 First time here?
  specproof quickstart     查看 30 秒上手路径 (无需任何配置)
  specproof demo            准备演示仓库, 打印下一步 (无需任何配置)
  specproof demo --run      直接跑第一次真实验证, 预期看到 BLOCKED 判定

\b
常用任务 Common tasks
  AI 改代码 (当前仓库):
    specproof craft run --repo . --spec-file requirement.txt
  验收一次代码变更 (前后两个版本):
    specproof verify --repo <仓库> --base main --head HEAD --spec <需求文件>
  探测模型服务可用能力:
    specproof probe   (需要 LLM_BASE_URL / LLM_API_KEY 环境变量)
  网页工作台 (演示数据 + 审批流, 需要 Docker):
    pwsh scripts/start_local.ps1

\b
结果怎么读 Reading the verdict
  VERIFIED   检查全部通过且有覆盖    BLOCKED  发现风险/回归, 需看证据
  FAILED     执行环境出错 (不代表代码对错)   UNVERIFIED  证据不足
"""


@click.group(epilog=HELP_EPILOG)
@click.version_option(version="0.1.0", prog_name="specproof")
def cli() -> None:
    """SpecProof — 用证据验收代码变更 (让 AI 按需求改代码; 独立检查变更是否符合需求).

    Spec 是需求, Proof 是验证需求的证据。每个子命令加 --help 可看详细参数。
    """


cli.add_command(demo)
cli.add_command(quickstart)
cli.add_command(probe)
cli.add_command(verify)
cli.add_command(replay)
cli.add_command(eval_cmd)
cli.add_command(contract_cmd)
cli.add_command(craft_cmd)
cli.add_command(baseline_cmd)
cli.add_command(fix_cmd)
cli.add_command(approve_cmd)
cli.add_command(mcp_cmd)
cli.add_command(devtools_cmd)


if __name__ == "__main__":
    cli()
