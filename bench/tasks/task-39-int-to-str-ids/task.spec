{
  "id": "task-39",
  "category": "code",
  "theme": "重构: 类型升级 int id → 规范化 str id",
  "appendix_e": "V-39",
  "trap": false,
  "title": "normalize_id 输出零填充的规范化字符串 id",
  "description": "normalize_id 目前返回 int。契约: 升级为接受 str|int 并返回 3 位零填充的字符串 (normalize_id(7) == '007'); 非数字输入抛 ValueError; 旧 int 路径经 int(normalize_id(x)) 可无损往返。",
  "acceptance_criteria": [
    "normalize_id(7) == '007'",
    "接受字符串数字输入",
    "非数字输入抛 ValueError"
  ],
  "forbidden_changes": [
    "不得改变 id 的数值语义 (仅表示形式升级)"
  ],
  "affected_area_hint": "svc.py"
}
