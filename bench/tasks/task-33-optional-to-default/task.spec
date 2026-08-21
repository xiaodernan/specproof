{
  "id": "task-33",
  "category": "code",
  "theme": "重构: 类型升级 Optional 参数 → 缺省值",
  "appendix_e": "V-33",
  "trap": false,
  "title": "greet 的 name 改为带缺省值的 str 参数",
  "description": "greet 目前要求显式传 name: str | None。契约: 签名升级为 name: str = 'guest', 无参调用返回 'Hello, guest'; 显式 None 与空串同样视为 guest。",
  "acceptance_criteria": [
    "无参调用 greet() 返回 'Hello, guest'",
    "None/空串按 guest 处理",
    "正常名字返回 'Hello, <name>'"
  ],
  "forbidden_changes": [
    "不得删除 greet 函数本身"
  ],
  "affected_area_hint": "svc.py"
}
