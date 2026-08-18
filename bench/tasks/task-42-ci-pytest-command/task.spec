{
  "id": "task-42",
  "category": "code",
  "theme": "真实工程: CI 配置 pytest 命令错误",
  "appendix_e": "V-42",
  "trap": false,
  "title": "CI 与构建脚本统一为 python -m pytest -q",
  "description": "build.ci_pytest_command 返回 'pytest tests', .github/workflows/ci.yml 里同样是裸 pytest (Windows 上 PATH 依赖不可靠)。契约: 两处统一为 'python -m pytest -q tests'。",
  "acceptance_criteria": [
    "ci_pytest_command() == 'python -m pytest -q tests'",
    "ci.yml 中不存在裸 'pytest tests' 命令",
    "ci.yml 包含 'python -m pytest -q tests'"
  ],
  "forbidden_changes": [
    "不得改动 ci.yml 其它步骤"
  ],
  "affected_area_hint": "build.py"
}
