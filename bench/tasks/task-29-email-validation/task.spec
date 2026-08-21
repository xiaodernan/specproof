{
  "id": "task-29",
  "category": "code",
  "theme": "多文件: API 输入校验 (邮箱)",
  "appendix_e": "V-29",
  "trap": false,
  "title": "validate_email 拒绝无 TLD/含空格的邮箱",
  "description": "api.validate_email 的正则过于宽松: 无 TLD ('a@b') 与含空格 ('a b@c.d')都放行。契约: 返回错误列表 (空列表 = 合法); 支持加号标签与子域名; 空串报错。",
  "acceptance_criteria": [
    "'a@b' 与含空格邮箱报错",
    "合法邮箱 (含 +tag 与子域) 通过",
    "空字符串报错"
  ],
  "forbidden_changes": [
    "不得引入第三方依赖 (仅标准库 re)"
  ],
  "affected_area_hint": "api.py"
}
