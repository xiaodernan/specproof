{
  "id": "task-rec-04",
  "category": "recovery",
  "theme": "恢复: 时间窗口两阶段 (解析→重叠判定)",
  "appendix_e": "V-R04",
  "trap": false,
  "title": "完成时间窗口的第二阶段",
  "description": "第一阶段 (parse_window) 已完成并写入审计记录; 第二阶段 overlaps 尚未实现。从 checkpoint 续跑: 判定两个 [start, end) 窗口是否重叠 (相接不算重叠)。",
  "acceptance_criteria": [
    "overlaps 正确判定重叠",
    "相接窗口不重叠",
    "第一阶段成果与审计记录不被重复执行"
  ],
  "forbidden_changes": [
    "不得修改 parse_window",
    "不得追加 audit.log 记录"
  ],
  "affected_area_hint": "svc.py",
  "recovery": {
    "job_id": "rec-04-job",
    "task_key": "generic",
    "last_green_step": "s2",
    "entries": [
      {
        "job_id": "rec-04-job",
        "step_id": "s1",
        "iteration": 0,
        "diagnosis": "",
        "edits_applied": [],
        "build_result": {
          "exit_code": 0,
          "failed_tests": [],
          "log_tail": ""
        },
        "verdict": "green",
        "timestamp": "2026-08-18T10:00:00+00:00"
      },
      {
        "job_id": "rec-04-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 parse_window",
        "edits_applied": [
          "svc.py"
        ],
        "build_result": {
          "exit_code": 0,
          "failed_tests": [],
          "log_tail": ""
        },
        "verdict": "progress",
        "timestamp": "2026-08-18T10:00:05+00:00"
      },
      {
        "job_id": "rec-04-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 parse_window",
        "edits_applied": [
          "svc.py"
        ],
        "build_result": {
          "exit_code": 0,
          "failed_tests": [],
          "log_tail": ""
        },
        "verdict": "green",
        "timestamp": "2026-08-18T10:00:06+00:00"
      }
    ],
    "memory_entries": [
      {
        "kind": "file_written",
        "detail": "svc.py",
        "step_id": "s2",
        "ts": "2026-08-18T10:00:06+00:00",
        "count": 1
      },
      {
        "kind": "decision",
        "detail": "步骤 s2 修复后 green (迭代 1)",
        "step_id": "s2",
        "ts": "2026-08-18T10:00:06+00:00",
        "count": 1
      }
    ]
  }
}
