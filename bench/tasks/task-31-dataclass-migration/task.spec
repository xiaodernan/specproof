{
  "id": "task-31",
  "category": "code",
  "theme": "重构: 接口迁移到 dataclass 请求对象",
  "appendix_e": "V-31",
  "trap": false,
  "title": "create_order 迁移到 OrderRequest 并保持旧调用兼容",
  "description": "create_order 目前只接受位置参数且丢弃 note。契约: 引入 OrderRequest dataclass (customer_id/items/note=''), create_order 接受它并返回完整订单; 旧的位置参数调用方式必须继续可用 (兼容包装)。",
  "acceptance_criteria": [
    "OrderRequest 传参可用且 note 保留",
    "旧位置参数调用继续可用",
    "空 customer_id 拒绝 (ValueError)"
  ],
  "forbidden_changes": [
    "不得删除旧的位置参数调用路径"
  ],
  "affected_area_hint": "svc.py"
}
