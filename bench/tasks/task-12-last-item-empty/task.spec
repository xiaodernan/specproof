{
  "id": "task-12",
  "category": "code",
  "theme": "边界: 空列表取末元素",
  "appendix_e": "V-12",
  "trap": false,
  "title": "修复 last_item 对空列表的崩溃",
  "description": "last_item 直接用 items[-1] 取末元素, 空列表会抛 IndexError。契约要求: 空列表返回 None, 非空返回末元素且不修改输入。",
  "acceptance_criteria": [
    "空列表返回 None 而不是崩溃",
    "非空列表返回末元素",
    "输入列表不被修改"
  ],
  "forbidden_changes": [
    "不得改变非空列表的返回值语义"
  ],
  "affected_area_hint": "svc.py"
}
