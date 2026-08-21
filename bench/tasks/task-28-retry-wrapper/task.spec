{
  "id": "task-28",
  "category": "code",
  "theme": "多文件: 服务层重试包装",
  "appendix_e": "V-28",
  "trap": false,
  "title": "call_with_retry 按次数重试并退避",
  "description": "service.call_with_retry 目前失败后直接返回 None, 从不重试。契约: 最多重试 retries 次, 每次失败后 sleep backoff 秒; 成功即返回; 耗尽后抛出最后一次异常。",
  "acceptance_criteria": [
    "失败后按 retries 次数重试",
    "两次尝试之间 sleep backoff",
    "耗尽重试后抛出最后一次异常"
  ],
  "forbidden_changes": [
    "不得吞掉异常 (耗尽后必须抛出)"
  ],
  "affected_area_hint": "service.py, api.py"
}
