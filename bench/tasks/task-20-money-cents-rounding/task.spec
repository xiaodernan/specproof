{
  "id": "task-20",
  "category": "code",
  "theme": "边界: 浮点金额转分舍入错误",
  "appendix_e": "V-20",
  "trap": false,
  "title": "to_cents 用半进位舍入避免浮点截断",
  "description": "to_cents 用 int(amount * 100) 直接截断, 19.99 之类会因浮点误差变成 1998。契约: 金额转分必须四舍五入 (half-up), 支持负数金额。",
  "acceptance_criteria": [
    "19.99 -> 1999 (浮点误差安全)",
    "2.675 -> 268 (half-up)",
    "负数金额正确转换"
  ],
  "forbidden_changes": [
    "不得引入第三方依赖 (仅标准库)"
  ],
  "affected_area_hint": "svc.py"
}
