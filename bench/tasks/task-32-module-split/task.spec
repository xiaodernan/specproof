{
  "id": "task-32",
  "category": "code",
  "theme": "重构: 模块拆分 (helper → utils.py)",
  "appendix_e": "V-32",
  "trap": false,
  "title": "把 add_tax 抽取到 utils.py 并消除 svc 内的重复定义",
  "description": "add_tax 的重复实现同时存在于 svc 与 utils 草稿之外。契约: add_tax 只定义在 utils.py (rate=0.08), svc.total_price 从 utils 导入使用; svc 内不得再保留自己的 add_tax 定义。",
  "acceptance_criteria": [
    "utils.add_tax 可用且算法正确",
    "svc 内不再有 add_tax 定义",
    "svc.total_price 结果不变"
  ],
  "forbidden_changes": [
    "不得改变 total_price 的对外行为"
  ],
  "affected_area_hint": "svc.py"
}
