{
  "id": "task-35",
  "category": "code",
  "theme": "重构: 重命名 + 弃用别名",
  "appendix_e": "V-35",
  "trap": false,
  "title": "fetch 重命名为 fetch_user 并保留弃用别名",
  "description": "契约: 新增 fetch_user 作为规范命名; 旧名 fetch 保留为弃用别名 (调用时发DeprecationWarning), 行为完全一致。",
  "acceptance_criteria": [
    "fetch_user 可用且行为正确",
    "fetch 别名继续可用",
    "fetch 调用发出 DeprecationWarning"
  ],
  "forbidden_changes": [
    "不得改变查找语义 (未命中返回 None)"
  ],
  "affected_area_hint": "svc.py"
}
