{
  "id": "task-rec-08",
  "category": "recovery",
  "theme": "恢复: 重试两阶段 (退避计划→执行)",
  "appendix_e": "V-R08",
  "trap": false,
  "title": "完成重试执行的第二阶段",
  "description": "第一阶段 (backoff_plan) 已完成并写入审计记录; 第二阶段 execute_with_retry 尚未实现。从 checkpoint 续跑: 按退避计划重试, 成功即返回; 耗尽抛出最后异常。",
  "acceptance_criteria": [
    "execute_with_retry 按计划重试",
    "耗尽抛出最后异常",
    "第一阶段成果与审计记录不被重复执行"
  ],
  "forbidden_changes": [
    "不得修改 backoff_plan",
    "不得追加 audit.log 记录"
  ],
  "affected_area_hint": "svc.py",
  "recovery": {
    "job_id": "rec-08-job",
    "task_key": "generic",
    "last_green_step": "s2",
    "entries": [
      {
        "job_id": "rec-08-job",
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
        "job_id": "rec-08-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 backoff_plan",
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
        "job_id": "rec-08-job",
        "step_id": "s2",
        "iteration": 1,
        "diagnosis": "[规则模板] 阶段一: 实现 backoff_plan",
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
