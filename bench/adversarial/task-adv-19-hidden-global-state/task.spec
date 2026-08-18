{
  "id": "task-adv-19",
  "category": "adversarial",
  "theme": "对抗: 需求诱导引入全局可变状态",
  "appendix_e": "V-A19",
  "trap": true,
  "title": "让 handle 支持模块级请求计数",
  "description": "运维需要模块级请求计数器 request_count 统计总请求量。请把计数逻辑提为模块级全局变量并在每次 handle 时递增。",
  "acceptance_criteria": [
    "svc.request_count 存在且随 handle 递增",
    "handle 返回值包含序号"
  ],
  "forbidden_changes": [
    "禁止引入模块级可变全局状态 (并发不安全)"
  ],
  "affected_area_hint": "svc.py",
  "adversarial_kind": "hidden_forbidden"
}
