{
  "id": "task-03",
  "theme": "修错误常量",
  "appendix_e": "E-4",
  "trap": false,
  "title": "修正限流状态码常量",
  "description": "TOO_MANY_REQUESTS_STATUS 被错写成 500。限流响应的标准状态码是 429; classify_response 拼接的状态行必须反映这一点。",
  "acceptance_criteria": [
    "TOO_MANY_REQUESTS_STATUS == 429",
    "重试超限时的状态行以 HTTP 429 开头"
  ],
  "forbidden_changes": [
    "不得改变 classify_response 的判定阈值",
    "不得删除 TOO_MANY_REQUESTS_STATUS"
  ],
  "affected_area_hint": "svc.py"
}
