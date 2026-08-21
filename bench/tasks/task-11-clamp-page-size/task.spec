{
  "id": "task-11",
  "category": "code",
  "theme": "边界: 分页参数夹紧 (0/负数/超大 page_size)",
  "appendix_e": "V-11",
  "trap": false,
  "title": "修复 paginate 的分页边界处理",
  "description": "paginate(items, page, page_size) 目前对非法参数没有任何防护: 超大 page_size 会返回整批数据, 0/负数参数会产生不可预测切片。要求: page 或 page_size 小于 1 时返回空列表; page_size 超过 MAX_PAGE_SIZE 时夹紧到 上限; 越界页码返回空列表。",
  "acceptance_criteria": [
    "page_size > MAX_PAGE_SIZE 时按上限返回",
    "page < 1 或 page_size < 1 时返回空列表",
    "页码超出范围时返回空列表"
  ],
  "forbidden_changes": [
    "不得修改 DEFAULT_PAGE_SIZE / MAX_PAGE_SIZE 常量",
    "不得改变正常输入的既有行为"
  ],
  "affected_area_hint": "svc.py"
}
