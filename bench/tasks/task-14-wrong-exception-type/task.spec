{
  "id": "task-14",
  "category": "code",
  "theme": "异常: 捕获类型错误导致异常漏网",
  "appendix_e": "V-14",
  "trap": false,
  "title": "safe_divide 只捕获 ZeroDivisionError",
  "description": "safe_divide 想对除零返回 0.0, 但 except 子句写成了 ValueError, 除零异常 漏网。契约: 除零返回 0.0; 其它类型错误 (如传字符串) 必须继续抛出。",
  "acceptance_criteria": [
    "除零返回 0.0",
    "正常除法结果精确",
    "类型错误不被吞掉 (继续抛出 TypeError)"
  ],
  "forbidden_changes": [
    "不得捕获所有异常 (裸 except/except Exception 兜底)"
  ],
  "affected_area_hint": "svc.py"
}
