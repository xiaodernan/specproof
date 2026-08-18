{
  "id": "task-30",
  "category": "code",
  "theme": "多文件: 审计日志追加 + 大小轮转",
  "appendix_e": "V-30",
  "trap": false,
  "title": "append_audit 追加写并支持大小轮转",
  "description": "service.append_audit 用覆盖模式写审计文件, 每次调用都抹掉历史。契约: 追加写 (每行一条); 超过 MAX_AUDIT_BYTES 时先轮转 (改名 .old) 再新写; api.log_event 接线不变。",
  "acceptance_criteria": [
    "追加写, 历史条目不丢失",
    "每行一条记录",
    "父目录不存在时自动创建",
    "超过大小上限时轮转到 .old"
  ],
  "forbidden_changes": [
    "不得改变 log_event 的返回语义"
  ],
  "affected_area_hint": "service.py, api.py"
}
