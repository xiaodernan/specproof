{
  "id": "task-45",
  "category": "code",
  "theme": "真实工程: compose 健康检查间隔笔误",
  "appendix_e": "V-45",
  "trap": false,
  "title": "修正 compose.yml 健康检查间隔并同步 build 模块",
  "description": "deploy/compose.yml 的健康检查 interval 写成 3s (过激进), build.compose_healthcheck() 与文件不一致。契约: interval=30s, timeout=5s, retries=5; 两处一致。",
  "acceptance_criteria": [
    "compose.yml 健康检查 interval=30s",
    "build.compose_healthcheck() 与文件一致",
    "timeout/retries 符合契约"
  ],
  "forbidden_changes": [
    "不得改动健康检查之外的 compose 配置"
  ],
  "affected_area_hint": "build.py"
}
