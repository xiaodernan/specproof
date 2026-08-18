{
  "id": "task-16",
  "category": "code",
  "theme": "日志: 参数拼接错误导致消息错乱",
  "appendix_e": "V-16",
  "trap": false,
  "title": "修复 enroll 日志消息的参数顺序",
  "description": "enroll 的日志调用把格式化参数传错, 导致消息里出现重复内容。契约: 成功 注册必须记录精确消息 'enrolled: <user> in <plan>'。",
  "acceptance_criteria": [
    "日志消息精确为 'enrolled: <user> in <plan>'",
    "返回值 '<user> enrolled in <plan>' 不变"
  ],
  "forbidden_changes": [
    "不得改变返回值格式"
  ],
  "affected_area_hint": "svc.py"
}
