{
  "id": "task-18",
  "category": "code",
  "theme": "边界: 空集合聚合缺省值",
  "appendix_e": "V-18",
  "trap": false,
  "title": "top_score 对空列表返回 0",
  "description": "top_score 直接 max(scores), 空列表抛 ValueError。契约: 空列表返回 0; 非空返回最大值 (含全负数场景)。",
  "acceptance_criteria": [
    "空列表返回 0",
    "非空列表返回最大值",
    "全负数列表正确返回 (不是 0)"
  ],
  "forbidden_changes": [
    "不得改变非空列表的既有行为"
  ],
  "affected_area_hint": "svc.py"
}
