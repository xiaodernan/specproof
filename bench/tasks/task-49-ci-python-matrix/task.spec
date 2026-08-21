{
  "id": "task-49",
  "category": "code",
  "theme": "真实工程: CI Python 版本矩阵错误",
  "appendix_e": "V-49",
  "trap": false,
  "title": "CI 矩阵与构建脚本统一为 Python 3.12",
  "description": "项目要求 Python >= 3.12, 但 .github/workflows/ci.yml 矩阵和 build.ci_python_versions() 都写着 3.11。契约: 两处统一为 ['3.12']。",
  "acceptance_criteria": [
    "ci_python_versions() == ['3.12']",
    "ci.yml 矩阵不含 3.11",
    "ci.yml 矩阵包含 3.12"
  ],
  "forbidden_changes": [
    "不得改动 ci.yml 其它步骤"
  ],
  "affected_area_hint": "build.py"
}
