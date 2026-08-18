{
  "id": "task-47",
  "category": "code",
  "theme": "真实工程: 打包清单误含测试",
  "appendix_e": "V-47",
  "trap": false,
  "title": "MANIFEST.in 排除测试目录",
  "description": "MANIFEST.in 把 tests/ 打进了源码包, build.manifest_rules() 与文件不一致。契约: 清单包含 src 源码、排除 tests/; 两处一致。",
  "acceptance_criteria": [
    "manifest_rules() 不含 'tests/' 包含规则",
    "MANIFEST.in 不含 'include tests'",
    "MANIFEST.in 包含 'include src/*'"
  ],
  "forbidden_changes": [
    "不得删除 MANIFEST.in 文件"
  ],
  "affected_area_hint": "build.py"
}
