{
  "id": "task-43",
  "category": "code",
  "theme": "真实工程: 容器镜像加固",
  "appendix_e": "V-43",
  "trap": false,
  "title": "Dockerfile 换 3.12-slim 基础镜像 + 非 root + 健康检查",
  "description": "Dockerfile 用 python:3.8-slim 且以 root 运行, 无健康检查。契约: 基础镜像换 python:3.12-slim; 建 appuser 并以 USER appuser 运行; 加 HEALTHCHECK; build.docker_base_image() 与文件保持一致。",
  "acceptance_criteria": [
    "基础镜像为 python:3.12-slim",
    "存在 USER appuser 且无 USER root",
    "存在 HEALTHCHECK"
  ],
  "forbidden_changes": [
    "不得删除 EXPOSE/CMD 既有步骤"
  ],
  "affected_area_hint": "build.py"
}
