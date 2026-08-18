{
  "id": "task-05",
  "theme": "补测试",
  "appendix_e": "E-6",
  "trap": false,
  "title": "为 upper_first 补边界测试模块",
  "description": "实现已存在但缺少文档化的边界测试。补齐 edge_cases.py 测试模块 (覆盖空串/单字符/首字母大写/unicode), 并保证测试套件全绿。",
  "acceptance_criteria": [
    "edge_cases.run_edge_cases 覆盖空串/单字符/大小写/unicode",
    "test_documented_edge_cases 通过"
  ],
  "forbidden_changes": [
    "不得修改 upper_first 的实现",
    "不得删除既有测试"
  ],
  "affected_area_hint": "svc.py"
}
