{
  "id": "task-50",
  "category": "code",
  "theme": "真实工程: 容器入口脚本信号处理",
  "appendix_e": "V-50",
  "trap": false,
  "title": "entrypoint.sh 以 exec 启动进程并保持 shebang",
  "description": "deploy/entrypoint.sh 缺 shebang 且不以 exec 启动 python, 信号无法转发给主进程。契约: 首行 #!/bin/sh; 末行以 exec 启动 python app.py; build.entrypoint_lines() 与文件一致。",
  "acceptance_criteria": [
    "首行 shebang #!/bin/sh",
    "末行 exec python app.py",
    "build.entrypoint_lines() 与文件一致"
  ],
  "forbidden_changes": [
    "不得把脚本改成其它解释器"
  ],
  "affected_area_hint": "build.py"
}
