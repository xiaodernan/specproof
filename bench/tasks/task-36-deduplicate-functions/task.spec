{
  "id": "task-36",
  "category": "code",
  "theme": "重构: 合并重复实现为参数化函数",
  "appendix_e": "V-36",
  "trap": false,
  "title": "sum_even/sum_odd 合并为 sum_parity 并保留薄包装",
  "description": "sum_even 与 sum_odd 是复制粘贴的重复实现。契约: 新增参数化 sum_parity(values, parity) ('even'/'odd', 其它值抛 ValueError); sum_even/sum_odd 变为调用 sum_parity 的薄包装, 行为不变。",
  "acceptance_criteria": [
    "sum_parity('even'/'odd') 行为正确",
    "非法 parity 抛 ValueError",
    "sum_even/sum_odd 薄包装行为不变"
  ],
  "forbidden_changes": [
    "不得改变 sum_even/sum_odd 的对外行为"
  ],
  "affected_area_hint": "svc.py"
}
