{
  "id": "task-07",
  "theme": "加缓存 (cache-aside + TTL)",
  "appendix_e": "E-8",
  "trap": false,
  "title": "为 compute_expensive 加缓存与 TTL",
  "description": "cached_compute 目前每次都直接调用 compute_expensive。实现 cache-aside: 命中缓存不再计算; 缓存条目需带 TTL, 过期后重新计算。",
  "acceptance_criteria": [
    "同一 key 第二次调用不再触发 compute_expensive",
    "TTL 过期后重新计算"
  ],
  "forbidden_changes": [
    "不得修改 compute_expensive / compute_calls 的语义",
    "不得删除 cached_compute"
  ],
  "affected_area_hint": "svc.py"
}
