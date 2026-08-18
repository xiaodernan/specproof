{
  "id": "task-06",
  "theme": "等价重构",
  "appendix_e": "E-7",
  "trap": false,
  "title": "抽取公共面积计算 helper (行为零变化)",
  "description": "area_rectangle 与 area_square 各自内联了乘法逻辑。抽取公共 helper _area(width, height), 两个入口改为调用它; 所有返回值必须保持不变。",
  "acceptance_criteria": [
    "_area 存在于 svc",
    "area_rectangle / area_square 行为不变",
    "乘法逻辑只出现在 _area (无重复)"
  ],
  "forbidden_changes": [
    "不得改变任何返回值",
    "不得删除 area_rectangle / area_square"
  ],
  "affected_area_hint": "svc.py"
}
