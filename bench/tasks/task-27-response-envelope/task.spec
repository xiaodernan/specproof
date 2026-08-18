{
  "id": "task-27",
  "category": "code",
  "theme": "多文件: 响应信封 camelCase 转换",
  "appendix_e": "V-27",
  "trap": false,
  "title": "to_envelope 把 snake_case 键转换为 camelCase",
  "description": "api.to_envelope 原样返回行字典, 外部契约要求 camelCase。契约: 递归转换嵌套 dict 的键; 无下划线键不变; 空 dict 原样返回。",
  "acceptance_criteria": [
    "user_id -> userId",
    "嵌套 dict 递归转换",
    "无下划线键与空 dict 不变"
  ],
  "forbidden_changes": [
    "不得修改输入 dict (返回新对象)"
  ],
  "affected_area_hint": "api.py"
}
