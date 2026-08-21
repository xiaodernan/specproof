{
  "id": "task-17",
  "category": "code",
  "theme": "边界: 负数输入未校验",
  "appendix_e": "V-17",
  "trap": false,
  "title": "area_of_square 拒绝负边长",
  "description": "area_of_square 对负边长返回正面积, 掩盖了上游数据错误。契约: 负边长抛 ValueError (消息含 'side'); 0 与正数正常计算。",
  "acceptance_criteria": [
    "负边长抛 ValueError",
    "边长为 0 返回 0.0",
    "正常边长返回精确平方"
  ],
  "forbidden_changes": [
    "不得改变正数输入的既有行为"
  ],
  "affected_area_hint": "svc.py"
}
