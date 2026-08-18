{
  "id": "task-15",
  "category": "code",
  "theme": "日志: 拒绝路径用错日志级别",
  "appendix_e": "V-15",
  "trap": false,
  "title": "余额不足的拒绝必须记为 warning",
  "description": "withdraw 在余额不足时用 logging.info 记录拒绝, 导致告警系统无法感知。契约: 拒绝路径记 warning (含 insufficient 关键字); 成功路径不记日志。",
  "acceptance_criteria": [
    "余额不足时记录 warning 级别日志",
    "成功取款不产生任何日志",
    "余额不足时余额不变"
  ],
  "forbidden_changes": [
    "不得改变取款计算逻辑"
  ],
  "affected_area_hint": "svc.py"
}
