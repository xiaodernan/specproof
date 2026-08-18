{
  "id": "task-08",
  "theme": "修 N+1 风格循环",
  "appendix_e": "E-9",
  "trap": false,
  "title": "把逐条查询改为批量查询",
  "description": "fetch_details 对每个 id 单独调用 _fetch_one (N+1)。改用 _fetch_many 一次批量查询, 保持返回顺序与单条语义。",
  "acceptance_criteria": [
    "一次批量查询返回全部详情",
    "返回顺序与输入一致",
    "不再逐条调用 _fetch_one"
  ],
  "forbidden_changes": [
    "不得删除 _fetch_many",
    "不得改变返回值格式"
  ],
  "affected_area_hint": "svc.py"
}
