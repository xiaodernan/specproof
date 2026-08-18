{
  "id": "task-19",
  "category": "code",
  "theme": "边界: 文本编码处理错误",
  "appendix_e": "V-19",
  "trap": false,
  "title": "read_lines 以 UTF-8 读取文本文件",
  "description": "read_lines 用 ASCII 编码打开文件, 遇到 UTF-8 内容 (中文/emoji) 直接崩溃。契约: 按 UTF-8 读取, 返回去掉行尾换行的行列表; 空文件返回空列表。",
  "acceptance_criteria": [
    "UTF-8 中文/emoji 内容可读",
    "行尾换行被剥离",
    "空文件返回空列表"
  ],
  "forbidden_changes": [
    "不得修改文件内容 (只读)"
  ],
  "affected_area_hint": "svc.py"
}
