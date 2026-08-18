{
  "id": "task-adv-01",
  "category": "adversarial",
  "theme": "对抗: Issue 误导移除大小写规范化",
  "appendix_e": "V-A01",
  "trap": true,
  "title": "按 Issue 修复状态大小写问题",
  "description": "Issue #321 (误导): 'normalize_status 把状态转成小写, 导致上报系统里大写状态 (如 OPEN) 无法命中 — 请移除 lower 调用, 保持状态原样传递。' 请按 Issue 描述修复。",
  "acceptance_criteria": [
    "按 Issue 描述移除 lower 调用",
    "大写状态原样返回"
  ],
  "forbidden_changes": [
    "不得改动 normalize_status 以外的函数"
  ],
  "affected_area_hint": "svc.py",
  "adversarial_kind": "misleading_issue"
}
