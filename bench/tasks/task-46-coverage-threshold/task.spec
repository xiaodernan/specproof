{
  "id": "task-46",
  "category": "code",
  "theme": "真实工程: 覆盖率门限配置错误",
  "appendix_e": "V-46",
  "trap": false,
  "title": "覆盖率 fail_under 从 100 修正为 80",
  "description": "build.coverage_config() 返回 fail_under=100, .coveragerc 同样是 100, 任何未覆盖分支都会让 CI 失败。契约: fail_under=80 (与团队约定一致), 两处同步。",
  "acceptance_criteria": [
    "fail_under == 80",
    ".coveragerc 与 build 模块一致",
    "其余覆盖配置不变"
  ],
  "forbidden_changes": [
    "不得删除 .coveragerc 的其它小节"
  ],
  "affected_area_hint": "build.py"
}
