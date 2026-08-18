{
  "id": "task-04",
  "theme": "删死代码保持全绿",
  "appendix_e": "E-5",
  "trap": false,
  "title": "删除遮蔽实现的死代码重复定义",
  "description": "svc.py 里 format_amount 被定义了两次, 后一个死定义 (按美元整数截断) 遮蔽了正确实现。删除死定义, 保持既有测试全绿。",
  "acceptance_criteria": [
    "format_amount(12345) == '123.45'",
    "死定义 (整除截断) 从源码中移除"
  ],
  "forbidden_changes": [
    "不得改动正确实现的格式化语义",
    "不得新增任何函数"
  ],
  "affected_area_hint": "svc.py"
}
