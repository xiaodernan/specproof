{
  "id": "task-26",
  "category": "code",
  "theme": "多文件: 配置优先级 (env > default)",
  "appendix_e": "V-26",
  "trap": false,
  "title": "resolve 让环境变量优先于默认值",
  "description": "config.resolve 无视环境变量直接返回默认值, api 拿不到注入配置。契约: env 中存在非空值时优先; 空值/缺失回退默认值; 默认值可为 None。",
  "acceptance_criteria": [
    "env 非空值优先于默认值",
    "env 空字符串视为缺失回退默认值",
    "env 缺失回退默认值 (含 None)"
  ],
  "forbidden_changes": [
    "不得改变 resolve 的函数签名"
  ],
  "affected_area_hint": "config.py, api.py"
}
