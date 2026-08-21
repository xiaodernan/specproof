{
  "id": "task-34",
  "category": "code",
  "theme": "重构: 依赖倒置 (注入时钟)",
  "appendix_e": "V-34",
  "trap": false,
  "title": "is_weekend 支持注入时钟函数",
  "description": "is_weekend 硬编码 time.localtime, 无法测试。契约: 新增可注入的 clock 参数 (默认 time.localtime); 传入返回 struct_time 的可调用对象; 周六/周日返回 True。",
  "acceptance_criteria": [
    "支持注入 clock 参数",
    "周六/周日 (tm_wday 5/6) 返回 True",
    "工作日返回 False"
  ],
  "forbidden_changes": [
    "不得改变默认行为 (无参调用仍可用)"
  ],
  "affected_area_hint": "svc.py"
}
