"""Refs that share no history with ``origin/master``, and what became of them.

Declarations only. Every number and every "still true" claim in here is
re-measured by
``tests/unit/test_branches_without_a_common_history_are_accounted_for.py``,
which owns the rulers; this module owns the adjudications. That split follows
``evidence/verdict_channels.py``: a register that also carries its own measuring
tool can never be caught disagreeing with the repository.

Why a register at all: #1547 reconciled these refs once, in a scratch probe, and
wrote the result into the ledger as prose. Prose does not expire. Two of the
claims it made were already soft by the time they were written — "three orphan
branches" is true at commit level and false at name level (four names reach the
three commits), and "every branch-only file has a master successor" is true only
if a successor is allowed to be a *different symbol at a different path*. Putting
the adjudications in a file that a gate re-measures turns both sentences into
facts that go red when master moves.

Three verdicts that must not be collapsed into one another:

``landed_at_other_path``
    master took the content, somewhere else. Declared by successor path *and*
    by a successor symbol the gate can grep.
``reversed_by_master``
    master looked at the same question and chose the opposite answer. This is
    not a gap; shipping the branch's version would undo a decision.
``not_landed`` / ``unadjudicated``
    no home was found, or a name-level difference was never resolved at the
    fact level. Both are gaps, and both must stay listed — a gap that is
    deleted from the register reads exactly like a gap that was fixed.

The last block (``DEF_CENSUS_BLIND_SPOTS``) is about the ruler, not the refs:
``\\bdef test_`` fires inside string literals, so an unanchored test-name census
counts fixtures as tests. What is registered here is the plane that actually
moves a census total -- the names the loose ruler prints that are not a test
definition anywhere in the tree -- with the files that print them.
"""

from __future__ import annotations

BASE_REF = "origin/master"

#: The commit the census ran against. The gate checks this is an ancestor of
#: HEAD (so the register cannot be authored against an arbitrary sha) but never
#: requires master to still be *at* it.
MEASURED_AT = "2e909ab5c91730aef7c8da23459c89d7c1e8babb"

#: peeled commit -> every ref name that reaches it.
#:
#: The key is a commit, not a name, because ``git merge-base`` answers for
#: commits: ``refs/tags/p0.5-verified-v1`` is an annotated tag object whose own
#: sha differs from the commit it peels to, so a name-keyed census reports 4
#: orphan "branches" where the repository holds 3 orphan lines of work.
ORPHAN_COMMITS: dict[str, tuple[str, ...]] = {
    "4145d95b78db4da56f6f8915a392f794ac4c23b7": (
        "refs/remotes/origin/release/p0.5-verified-v1",
        "refs/tags/p0.5-verified-v1",
    ),
    "a756f533872b6de9750d3ff584825461980be60b": (
        "refs/remotes/origin/feature/p1-reliability-kernel",
    ),
    "76285a7d37089b588e977cea1de90f807bcecc12": (
        "refs/remotes/origin/feature/interview-hardening",
    ),
}

VERDICTS: frozenset[str] = frozenset({
    "landed_at_other_path",
    "succeeded_by_rewrite",
    "reversed_by_master",
    "not_landed",
    "unadjudicated",
})

#: "<sha12>:<branch-only path>" -> the adjudication.
#:
#: ``successor_paths`` are checked to exist in the base tree; ``successor_symbols``
#: are checked with ``git grep -w`` in the base tree. Both are declared per file so
#: a reader can see *what* was believed to have landed, not only that something was.
FILE_DISPOSITIONS: dict[str, dict[str, object]] = {
    # ── release/p0.5-verified-v1 (4145d95) ─────────────────────────────────
    "4145d95b7:evidence/matrix.py": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("agent/matrix_policy.py", "agent/nodes/build_matrix.py"),
        "successor_symbols": ("_severity_rank", "build_matrix_node"),
        "reason": ("分支侧定义 2 个符号：_severity_rank 按原名住在 agent/matrix_policy.py，"
                    "build_evidence_matrix 原名在 master 0 处出现，矩阵内容以 "
                    "agent/nodes/build_matrix.py 的 build_matrix_node 接续"
                    " —— 名字级缺席、事实级接续"),
    },
    "4145d95b7:scripts/run_differential.sh": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("agent/nodes/run_differential.py",),
        "successor_symbols": ("run_differential",),
        "reason": ("shell 包装脚本定义 0 个函数，差分执行的内容在 master 的 agent 节点里："
                    "同词干后继 agent/nodes/run_differential.py 存在"),
    },
    # ── feature/p1-reliability-kernel (a756f53) ────────────────────────────
    "a756f5338:.github/workflows/quality.yml": {
        "verdict": "unadjudicated",
        "successor_paths": (".github/workflows/ci.yml",),
        "successor_symbols": (),
        "reason": ("名字级缺席 2 个：docker-integration 与 unit-and-integration 仍无对应；"
                   "provider-smoke 已由 master ci.yml 的同名 job 承接（#1549 落地，"
                   "分支 4 个 step 逐个照抄，env 键是 providers/config.py 声明的 3 个名字），"
                   "lint-and-type 与 lint-type 是改名。缺席数是"
                   "test_the_provider_smoke_ci_leg_carries_the_branch_job.py 重量的第一个整数"),
    },
    "a756f5338:Dockerfile.api": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("docker/Dockerfile.api",),
        "successor_symbols": (),
        "reason": ("分支根目录的该路径在 master 树 0 处；同名文件住在 docker/ 下，"
                    "两边非注释行 14 与 19、逐行相同 4 行 —— 位置接续、内容重写"),
    },
    "a756f5338:compose.p1.yml": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("compose.phase0.yml", "compose.production.yml"),
        "successor_symbols": (),
        "reason": ("按 YAML 解析的 6 个 service（api/mysql/outbox-relay/rabbitmq/redis/worker）"
                    "在 master 的 compose 文件全集 16 个里缺席 0 个 —— 文件名没接续，内容全接续"),
    },
    "a756f5338:docs/p1/p1a-final-report.md": {
        "verdict": "not_landed",
        "successor_paths": (),
        "successor_symbols": (),
        "reason": "master 树里 docs/p1/ 前缀 0 个路径；P1 阶段报告没有接续者，也不该伪装成有",
    },
    "a756f5338:docs/p1/wip-migration-matrix.md": {
        "verdict": "not_landed",
        "successor_paths": (),
        "successor_symbols": (),
        "reason": "同上：docs/p1/ 前缀 0 个路径，迁移矩阵是分支自用的过程文档",
    },
    "a756f5338:storage/migrations/001_p1_baseline.sql": {
        "verdict": "succeeded_by_rewrite",
        "successor_paths": ("storage/migrations/001_job_state_machine.sql",
                             "storage/migrations/002_outbox.sql"),
        "successor_symbols": ("stale_replaced_by", "worker_id", "retry_count"),
        "reason": ("分支迁移声明 15 个表/列/索引名：14 个在 master 全树找得到家、只有 5 个在"
                    " master 自己的 2 个迁移文件里；config_hash 全树 0 处。分支占用的 001/002 "
                    "编号在 master 已被 2 个不同内容的迁移占用 —— 所以按名字搬会撞号"),
    },
    "a756f5338:storage/migrations/002_failed_terminal.sql": {
        "verdict": "reversed_by_master",
        "successor_paths": ("storage/mysql.py",),
        "successor_symbols": ("_VALID_TRANSITIONS",),
        "reason": ("分支 SQL 自述 FAILED 出边由 2 个改成 0 个且称代码已应用；master 实测 "
                    "_VALID_TRANSITIONS['FAILED'] 有 4 条出边且含 QUEUED —— 判决相反，不搬"),
    },
    "a756f5338:tests/integration/test_fault_scenarios.py": {
        "verdict": "not_landed",
        "successor_paths": (),
        "successor_symbols": (),
        "reason": ("锚定尺子量出 18 个 test def，master 树里该路径 0 处存在；"
                    "这是 58 个名字级差异里唯一一个整文件未接续的 18 个，排在 #1550 接手"),
    },
    "a756f5338:evidence/matrix.py": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("agent/matrix_policy.py", "agent/nodes/build_matrix.py"),
        "successor_symbols": ("_severity_rank", "build_matrix_node"),
        "reason": "与 4145d95 的同一文件同判：2 个符号里 1 个原名有家、1 个改名接续",
    },
    "a756f5338:scripts/run_differential.sh": {
        "verdict": "landed_at_other_path",
        "successor_paths": ("agent/nodes/run_differential.py",),
        "successor_symbols": ("run_differential",),
        "reason": "与 4145d95 的同一文件同判：0 个 shell 函数，内容在同词干的 agent 节点",
    },
}

#: "<sha12>:<path>::<branch test name>" -> the master test name that carries the
#: same fact. Adjudicated by hand from a near-name candidate list; the gate
#: measures both sides exist, so a pair that rots goes red rather than rotting
#: quietly in prose.
RENAMED_TESTS: dict[str, str] = {
    "4145d95b7:tests/integration/test_differential.py::test_run_static_checks_detects_auth_bypass":
        "test_contract_checkers_detect_auth_bypass",
    "a756f5338:tests/integration/test_differential.py::test_run_static_checks_detects_auth_bypass":
        "test_contract_checkers_detect_auth_bypass",
    "a756f5338:tests/unit/test_job_state_machine.py::test_all_10_statuses_exist":
        "test_all_ten_statuses_defined",
    "a756f5338:tests/unit/test_job_state_machine.py::test_invalid_transitions":
        "test_invalid_transitions_are_rejected",
    "a756f5338:tests/unit/test_job_state_machine.py::test_invalid_transition_is_exception":
        "test_invalid_transitions_are_rejected",
    "a756f5338:tests/unit/test_job_state_machine.py::test_terminal":
        "test_is_terminal",
    "a756f5338:tests/unit/test_job_state_machine.py::test_non_terminal":
        "test_is_terminal",
    "a756f5338:tests/unit/test_job_state_machine.py::test_valid_transitions":
        "test_valid_transitions_are_recognized",
    "76285a7d3:tests/unit/test_job_state_machine.py::test_mark_stale_for_head":
        "test_mark_stale_for_head_supersedes_one_repo",
    "76285a7d3:tests/unit/test_python_adapter.py::test_matrix_row_python_is_supported_local_first":
        "test_matrix_row_python_is_sandboxed",
    "76285a7d3:tests/unit/test_repo_safety.py::test_junction_escape_detected":
        "test_directory_link_escape_detected",
    "76285a7d3:tests/unit/test_repo_safety.py::test_junction_inside_repo_passes":
        "test_directory_link_inside_repo_passes",
    "76285a7d3:tests/unit/test_checker_fixes.py::test_token_call_removed_but_method_kept_is_detected":
        "test_token_invalidation_guard_removed_is_detected",
    "76285a7d3:tests/unit/test_tenant_auth.py::test_repository_get_job_unscoped_sql_unchanged":
        "test_repository_get_job_unscoped_injects_no_tenant_predicate",
}

#: The name-level census of the three orphan commits, measured with the anchored
#: def ruler and split by whether master owns the file the name lives in.
#: ``shared_file`` names may be explained by ``RENAMED_TESTS`` or left unexplained;
#: the gate recomputes all four numbers and refuses to certify if they move.
NAME_ONLY_CENSUS: dict[str, int] = {
    "total": 58,
    "shared_file": 40,
    "branch_only_file": 18,
    "unexplained_after_renames": 26,
}

#: branch job name -> master job id that carries the same step. The gate measures
#: the master side exists as a job id in one of master's workflow files.
RENAMED_JOBS: dict[str, str] = {
    "lint-and-type": "lint-type",
}

#: Every content-level gap, keyed by the exact token the gate re-measures: a SQL
#: symbol with no home, a branch job name master never took, or a branch-only file
#: whose verdict is ``not_landed``. Deleting a key has to be a decision someone can
#: see -- a gap removed from the register reads exactly like a gap that was fixed.
REGISTERED_GAPS: dict[str, str] = {
    "config_hash": "分支迁移声明的 15 个名字里唯一在 master 全树 0 处命中的列名",
    # provider-smoke was this dict's only workflow-shaped key. #1549 carried the
    # branch's job over into master's ci.yml step-for-step, so the name is no
    # longer absent -- and P8 re-derives that from the refs, not from here.
    "docker-integration": "quality.yml 的 job 名，master 的 9 个 job id 里 0 个同名，未判定承接者",
    "unit-and-integration": "quality.yml 的 job 名，master 的 9 个 job id 里 0 个同名",
    "docs/p1/p1a-final-report.md": "master 的 docs/p1/ 前缀 0 个路径，阶段报告无承接者",
    "docs/p1/wip-migration-matrix.md": "master 的 docs/p1/ 前缀 0 个路径，迁移矩阵无承接者",
    "tests/integration/test_fault_scenarios.py": (
        "锚定尺子 18 个 test def，master 树 0 处该路径；#1550 接手"),
}

#: Where an unanchored ``\bdef test_`` census prints a name that is not a test
#: definition anywhere in the tree -- prose counted as a test. The values are
#: exactly those names, per file. Per file the two rulers disagree in more files
#: than this (a name invented in one file and genuinely defined in another is
#: not a census error), so the population here is the tree-wide difference, not
#: the sum of the per-file differences.
DEF_CENSUS_BLIND_SPOTS: dict[str, tuple[str, ...]] = {
    "tests/unit/test_bench_aider.py": ("test_fake", "test_x"),
    "tests/unit/test_bench_craft.py": ("test_a", "test_b"),
    "tests/unit/test_craft_gates_dispatch_every_kind_the_vocabulary_names.py": ("test_x",),
    "tests/unit/test_edit_anchor_and_verify_target.py": ("test_config",),
    "tests/unit/test_edit_test_guard.py": ("test_x",),
    "tests/unit/test_mysql_usage_report.py": ("test_x",),
    "tests/unit/test_path_suffix_resolve.py": ("test_config",),
    "tests/unit/test_scrape_roster_ports_answer_their_own_numbers.py": ("test_L2", "test_x"),
    "tests/unit/test_swebench_deps_pins.py": ("test_config",),
    "tests/unit/test_verify_criterion_anchor.py": ("test_blueprints",),
}
