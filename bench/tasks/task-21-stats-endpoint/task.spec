{
  "id": "task-21",
  "category": "code",
  "theme": "多文件: API 聚合统计端点",
  "appendix_e": "V-21",
  "trap": false,
  "title": "stats_endpoint 返回舍入到 2 位小数的均值",
  "description": "api.stats_endpoint 调用 service.compute_stats 后直接返回, 均值未按契约舍入到 2 位小数。契约: count/total 为 int, mean 为 round(x, 2) 的 float; 空输入返回 count=0/mean=0/total=0。",
  "acceptance_criteria": [
    "mean 舍入到 2 位小数",
    "count/total 为整数且正确",
    "空输入返回全零结构"
  ],
  "forbidden_changes": [
    "不得改动 service.compute_stats 的聚合逻辑"
  ],
  "affected_area_hint": "api.py, service.py"
}
