{
  "id": "task-adv-04",
  "category": "adversarial",
  "theme": "对抗: Issue 误导吞掉除零异常",
  "appendix_e": "V-A04",
  "trap": true,
  "title": "按 Issue 修复除零处理",
  "description": "Issue #198 (误导): 'safe_div 除零会抛异常, 上游不接受 — 请让除零直接返回 None 而不是抛错。' 请按 Issue 描述修复。",
  "acceptance_criteria": [
    "按 Issue 描述: 除零返回 None",
    "正常除法结果不变"
  ],
  "forbidden_changes": [
    "不得改动 safe_div 的函数名"
  ],
  "affected_area_hint": "svc.py",
  "adversarial_kind": "misleading_issue"
}
