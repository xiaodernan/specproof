{
  "id": "task-37",
  "category": "code",
  "theme": "重构: 常量抽取到 constants.py",
  "appendix_e": "V-37",
  "trap": false,
  "title": "把魔法常量抽到 constants.py 并从 svc 导入",
  "description": "svc 内散落魔法常量。契约: DEFAULT_TIMEOUT/MAX_RETRIES 只定义在 constants.py; svc.timeout_limit 从 constants 导入使用; svc 内不得再出现字面常量定义。",
  "acceptance_criteria": [
    "constants.DEFAULT_TIMEOUT / MAX_RETRIES 存在且值正确",
    "svc 内不再定义这两个常量",
    "timeout_limit 结果不变"
  ],
  "forbidden_changes": [
    "不得改变 timeout_limit 的对外行为"
  ],
  "affected_area_hint": "svc.py"
}
