{
  "id": "task-38",
  "category": "code",
  "theme": "重构: 元组返回 → dataclass 结果对象",
  "appendix_e": "V-38",
  "trap": false,
  "title": "stats 返回 StatsResult dataclass 并保持解包兼容",
  "description": "stats 返回裸元组 (count, mean)。契约: 返回 StatsResult dataclass (count/mean 字段), 且旧式解包 a, b = stats(...) 继续可用; 空列表返回 (0, 0.0)。",
  "acceptance_criteria": [
    "返回对象有 count/mean 字段",
    "旧式元组解包继续可用",
    "空列表返回 0/0.0"
  ],
  "forbidden_changes": [
    "不得改变统计口径"
  ],
  "affected_area_hint": "svc.py"
}
