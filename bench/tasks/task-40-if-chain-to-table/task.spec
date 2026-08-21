{
  "id": "task-40",
  "category": "code",
  "theme": "重构: if 链 → 表驱动 (行为零变化)",
  "appendix_e": "V-40",
  "trap": false,
  "title": "tier 改为表驱动实现并保持边界行为完全一致",
  "description": "tier 用一长串 if 判断评分等级。契约: 重构为表驱动 (TIER_TABLE 常量), 行为零变化; svc 内不得保留 if 链。",
  "acceptance_criteria": [
    "TIER_TABLE 常量存在",
    "边界行为与重构前完全一致 (90/80/70 及相邻值)",
    "svc 内不再保留 if 链"
  ],
  "forbidden_changes": [
    "不得改变任何评分映射行为"
  ],
  "affected_area_hint": "svc.py"
}
