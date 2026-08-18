{
  "id": "task-rec-07",
  "category": "recovery",
  "theme": "恢复: 报告两阶段 (采集→渲染)",
  "appendix_e": "V-R07",
  "trap": false,
  "title": "完成报告渲染的第二阶段",
  "description": "第一阶段 (collect_metrics) 已完成并写入审计记录; 第二阶段 render_report 尚未实现。从 checkpoint 续跑: 把指标渲染为 'name=value' 行, 以换行连接, 末尾带换行。",
  "acceptance_criteria": [
    "render_report 输出 name=value 行",
    "空指标返回空字符串",
    "第一阶段成果与审计记录不被重复执行"
  ],
  "forbidden_changes": [
    "不得修改 collect_metrics",
    "不得追加 audit.log 记录"
  ],
  "affected_area_hint": "svc.py",
  "recovery": {
    "job_id": "rec-07-job",
    "task_key": "generic",
    "last_green_step": "s2",
    "entries": [
      {
        "job_id": "rec-07-job",
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
        "job_id": "rec-07-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 collect_metrics",
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
        "job_id": "rec-07-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 collect_metrics",
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
