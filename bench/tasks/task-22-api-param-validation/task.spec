{
  "id": "task-22",
  "category": "code",
  "theme": "多文件: API 层参数校验",
  "appendix_e": "V-22",
  "trap": false,
  "title": "get_page 在 API 层校验分页参数",
  "description": "api.get_page 把查询参数原样传给 service.slice_items, 负数/非数字 page 会穿透到服务层。契约: API 层校验 page/page_size 为正整数, 非法参数抛 ValueError; service.slice_items 只接收合法整数并夹紧 page_size 上限。",
  "acceptance_criteria": [
    "page/page_size 非法 (负数/非数字/0) 抛 ValueError",
    "合法参数正确分页",
    "service 层夹紧超大 page_size"
  ],
  "forbidden_changes": [
    "不得改变 service.slice_items 的函数签名"
  ],
  "affected_area_hint": "api.py, service.py"
}
