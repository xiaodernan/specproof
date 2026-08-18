{
  "id": "task-48",
  "category": "code",
  "theme": "真实工程: 部署脚本环境变量名笔误",
  "appendix_e": "V-48",
  "trap": false,
  "title": "app_port 读取 APP_PORT 而不是 PORT",
  "description": "deploy.app_port 读环境变量 PORT, 但部署契约约定的变量名是 APP_PORT。契约: 读取 APP_PORT, 缺省 8000; PORT 变量必须被忽略。",
  "acceptance_criteria": [
    "APP_PORT 生效",
    "缺省值为 '8000'",
    "PORT 变量被忽略"
  ],
  "forbidden_changes": [
    "不得改变返回值类型 (str)"
  ],
  "affected_area_hint": "deploy.py"
}
