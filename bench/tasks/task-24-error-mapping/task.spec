{
  "id": "task-24",
  "category": "code",
  "theme": "多文件: 服务异常到 API 错误映射",
  "appendix_e": "V-24",
  "trap": false,
  "title": "user_endpoint 把 NotFoundError 映射为 404",
  "description": "api.user_endpoint 用 except Exception 吞掉所有异常并返回 500, 用户不存在时也返回 500。契约: service.NotFoundError 映射为 404 (body 含 'not_found');存在时返回 200; 其它异常必须继续传播, 不得吞掉。",
  "acceptance_criteria": [
    "用户不存在 -> 404 + 'not_found'",
    "用户存在 -> 200 + 用户数据",
    "非 NotFoundError 异常继续传播"
  ],
  "forbidden_changes": [
    "不得捕获所有异常 (except Exception 兜底)"
  ],
  "affected_area_hint": "api.py, service.py"
}
