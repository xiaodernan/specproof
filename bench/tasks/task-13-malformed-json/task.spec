{
  "id": "task-13",
  "category": "code",
  "theme": "异常: 畸形输入健壮处理",
  "appendix_e": "V-13",
  "trap": false,
  "title": "parse_payload 对畸形 JSON 返回空字典并记录警告",
  "description": "parse_payload 直接 json.loads, 畸形输入会让调用方崩溃。契约: 解析失败或 结果不是 dict 时返回 {} 并记录一条 warning 日志, 合法 dict 原样返回。",
  "acceptance_criteria": [
    "畸形 JSON 返回 {} 并记录 warning",
    "合法 JSON 对象原样返回",
    "非对象 JSON (如数字/字符串) 同样返回 {}"
  ],
  "forbidden_changes": [
    "不得静默吞掉其它异常类型 (只处理 JSONDecodeError)"
  ],
  "affected_area_hint": "svc.py"
}
