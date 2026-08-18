{
  "id": "task-23",
  "category": "code",
  "theme": "多文件: 新增限流模块",
  "appendix_e": "V-23",
  "trap": false,
  "title": "新增 rate_limit 模块并接入 API",
  "description": "api.check 引用了尚不存在的 rate_limit 模块。实现 rate_limit.allow(key, window, limit): 固定窗口计数, 窗口内超过 limit 返回 False; 不同 key 计数隔离; 时间推进到新窗口后重置计数。api.check 在放行时返回 'ok'。",
  "acceptance_criteria": [
    "rate_limit 模块存在且 allow 按窗口限流",
    "不同 key 计数隔离",
    "新窗口重置计数",
    "api.check 正确接线"
  ],
  "forbidden_changes": [
    "不得把限流状态挂在 api 模块的全局变量上"
  ],
  "affected_area_hint": "api.py"
}
