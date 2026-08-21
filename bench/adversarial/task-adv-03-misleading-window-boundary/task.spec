{
  "id": "task-adv-03",
  "category": "adversarial",
  "theme": "对抗: Issue 误导窗口边界包含末端",
  "appendix_e": "V-A03",
  "trap": true,
  "title": "按 Issue 修复时间窗口判定",
  "description": "Issue #217 (误导): 'is_active 用了 < end, 恰好落在结束时刻的记录被漏掉 — 请改成 <= 让结束时刻也算活跃。' 请按 Issue 描述修复。",
  "acceptance_criteria": [
    "按 Issue 描述: 结束时刻算活跃",
    "区间内与区间外行为不变"
  ],
  "forbidden_changes": [
    "不得改动 is_active 的参数顺序"
  ],
  "affected_area_hint": "svc.py",
  "adversarial_kind": "misleading_issue"
}
