"""Tool-call quality self-check (Hermes-class advantage #2).

The model's JSON Action Envelope is validated BEFORE execution against the
versioned registry schema: tool name exists, version matches, arguments
satisfy the declared type/range constraints. An invalid envelope is never
executed — the checker emits ONE deterministic retry instruction (to be
appended to the prompt) and asks the injected producer callable again; a
second invalid envelope gives up carrying the stable error code.

Design:

- pure functions (validate_envelope / retry_instruction) + an injected
  callable (EnvelopeProducer) — zero live LLM calls, fully unit-testable;
- duck-typed from_registry() adapts craft.tools.ToolRegistry without
  importing craft, so providers never depends on craft (no import cycle);
- error codes mirror the stable registry codes of craft/tools.py
  (UNKNOWN_TOOL / TOOL_VERSION_MISMATCH / INVALID_ARGUMENTS) so a give-up
  carries the exact code the registry would have produced;
- counters {attempts, valid, retried, success} plus a tool-call success
  rate are exposed via metrics() for craft/loop to log.

Envelope contract (JSON Action Envelope):

    {"action": "<tool_name>", "version": <int>, "params": {...}}

"version" is optional: absent means "stamp the registered version"
(mirroring ToolRegistry.build_tool_call(version=None)). Unknown top-level
keys are ignored (same forward-compatibility policy as craft/schemas.py).

Edit-proposal contract (SpecCraft M2 diagnose-fix, 首跑缺口修复):

    {"diagnosis": "<one sentence>",
     "edits": [{"action": "apply_edit", "path": ...,
               "old": ..., "new": ...}, ...]}

A bare [...] array is also accepted (diagnosis empty). EditProposalSelfCheck
applies the same ONE-retry-then-give-up state machine to the edit proposal:
an invalid proposal is never executed, exactly one deterministic repair
instruction (edit_retry_instruction) is handed back to the injected model
round-trip, and a second invalid proposal gives up carrying the stable code
LLM_PROPOSAL_INVALID. Unparseable model text is carried as a
ProposalParseFailure with a bounded snippet of the raw output.

Test-file guard (W112): the harness applies each SWE-bench instance's test
patch itself, so any edit op whose repo-relative path matches tests/** or
test_*.py / *_test.py is rejected with CODE_TEST_FILE_FORBIDDEN and the
repair instruction steers the model to a source-only fix.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

#: Stable error codes — mirrors of craft.tools' registry codes (the single
#: source of truth). Duplicated here on purpose: providers must not import
#: craft (craft.llm imports providers; a providers -> craft edge would close
#: the cycle).
CODE_UNKNOWN_TOOL = "UNKNOWN_TOOL"
CODE_VERSION_MISMATCH = "TOOL_VERSION_MISMATCH"
CODE_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
#: Stable code for an edit proposal that failed validation after its ONE
#: repair retry (M2 diagnose-fix path; the loop fails the step with M1
#: semantics carrying this code).
CODE_PROPOSAL_INVALID = "LLM_PROPOSAL_INVALID"
#: Stable code for an edit op targeting a test file (W112): the harness
#: applies each instance's test patch itself, so craft must never create
#: or modify test files — the repair instruction steers the model to a
#: source-only fix instead.
CODE_TEST_FILE_FORBIDDEN = "TEST_FILE_FORBIDDEN"


@dataclass(frozen=True)
class ProposalParseFailure:
    """Raw model reply that could not be parsed as JSON at all.

    Carries a bounded tail of the raw text so the repair instruction can
    show the model exactly what went wrong — never the full reply.
    """

    snippet: str

ParamKind = Literal["str", "int", "bool", "list[str]"]


@dataclass(frozen=True)
class ParamSchema:
    """Declared shape of one tool argument (mirrors craft.tools.Param)."""

    name: str
    kind: ParamKind
    required: bool = False
    max_len: int | None = None
    min_value: int | None = None
    max_value: int | None = None


@dataclass(frozen=True)
class ToolSchema:
    """Declared shape of one tool (mirrors craft.tools.ToolSpec)."""

    name: str
    version: int
    params: tuple[ParamSchema, ...]


@dataclass(frozen=True)
class CheckOutcome:
    """Validation verdict.

    status: valid  — envelope conforms, safe to execute;
            retry  — invalid, ONE repair instruction is available;
            give_up — the retried envelope was invalid again; code carries
                     the stable registry error code of the offense.
    """

    status: Literal["valid", "retry", "give_up"]
    code: str
    message: str
    tool: str
    version: int


RegistrySchema = Mapping[str, ToolSchema]

#: The injected model round-trip: given the retry instruction (or None on
#: the first attempt) return the raw envelope the model produced.
EnvelopeProducer = Callable[[str | None], object]


def _retry(code: str, message: str, tool: str, version: int) -> CheckOutcome:
    return CheckOutcome(
        status="retry", code=code, message=message, tool=tool, version=version
    )


def _check_param(param: ParamSchema, value: Any) -> str:
    """Empty string when valid, else the violation message (no tool prefix)."""
    if param.kind == "str":
        if not isinstance(value, str):
            return f"{param.name} 应为字符串"
        if param.max_len is not None and len(value) > param.max_len:
            return f"{param.name} 超过长度上限 {param.max_len}"
    elif param.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{param.name} 应为整数"
        if param.min_value is not None and value < param.min_value:
            return f"{param.name} 应 ≥ {param.min_value}"
        if param.max_value is not None and value > param.max_value:
            return f"{param.name} 应 ≤ {param.max_value}"
    elif param.kind == "bool":
        if not isinstance(value, bool):
            return f"{param.name} 应为布尔值"
    else:  # list[str]
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            return f"{param.name} 应为字符串数组"
        if param.max_len is not None and len(value) > param.max_len:
            return f"{param.name} 超过元素上限 {param.max_len}"
    return ""


def _validate_params(spec: ToolSchema, params: dict[str, Any]) -> str:
    """Strict argument validation mirroring craft.tools.validate_params."""
    known = {param.name for param in spec.params} | {"reason"}
    unknown = sorted(key for key in params if key not in known)
    if unknown:
        return f"{spec.name} 参数非法: 未知键 {unknown}"
    for param in spec.params:
        if param.name not in params:
            if param.required:
                return f"{spec.name} 参数非法: 缺少必填参数 {param.name}"
            continue
        message = _check_param(param, params[param.name])
        if message:
            return f"{spec.name} 参数非法: {message}"
    reason = params.get("reason")
    if reason is not None and not isinstance(reason, str):
        return f"{spec.name} 参数非法: reason 应为字符串"
    return ""


def validate_envelope(schemas: RegistrySchema, envelope: object) -> CheckOutcome:
    """Pure envelope validation: tool name -> version -> argument schema.

    Returns CheckOutcome with status "valid" or "retry"; the stateful
    ToolCallSelfCheck turns a second consecutive "retry" into "give_up".
    """
    if not isinstance(envelope, dict):
        return _retry(CODE_INVALID_ARGUMENTS, "信封不是 JSON 对象", "", 0)
    action = envelope.get("action")
    if not isinstance(action, str) or not action.strip():
        return _retry(CODE_UNKNOWN_TOOL, "信封缺少工具名 action", "", 0)
    spec = schemas.get(action)
    if spec is None:
        return _retry(CODE_UNKNOWN_TOOL, f"未知工具 {action!r} (未注册)", action, 0)

    raw_version = envelope.get("version")
    version = spec.version if raw_version is None else raw_version
    if isinstance(version, bool) or not isinstance(version, int):
        return _retry(
            CODE_VERSION_MISMATCH,
            f"{action}: version 应为整数 (注册 v{spec.version})",
            action,
            0,
        )
    if version != spec.version:
        return _retry(
            CODE_VERSION_MISMATCH,
            f"{action}: 版本不匹配 (请求 v{version}, 注册 v{spec.version})",
            action,
            version,
        )

    params = envelope.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _retry(
            CODE_INVALID_ARGUMENTS, f"{action} 参数非法: params 应为 JSON 对象",
            action, version,
        )
    message = _validate_params(spec, params)
    if message:
        return _retry(CODE_INVALID_ARGUMENTS, message, action, version)
    return CheckOutcome(
        status="valid", code="", message="", tool=action, version=version
    )



def retry_instruction(outcome: CheckOutcome) -> str:
    """ONE deterministic repair instruction for the model (append to prompt)."""
    return (
        "TOOL CALL SELF-CHECK — your tool call was REJECTED and NOT executed.\n"
        f"error code: [{outcome.code}] {outcome.message}\n"
        "Repair rule: respond with exactly ONE corrected JSON Action Envelope of "
        'the form {"action": "<tool_name>", "version": <int>, "params": {...}} — '
        "the tool name must be registered, version must equal the registered "
        "version, and every param must satisfy the declared type/range schema. "
        "No markdown fences, no prose, nothing but the JSON object."
    )



def schemas_from_registry(registry: object) -> dict[str, ToolSchema]:
    """Adapt a duck-typed tool registry (craft.tools.ToolRegistry) to schemas.

    Accepts an object exposing specs() -> mapping of spec objects carrying
    name/version/params (each param: name/kind/required/max_len/min_value/
    max_value), or a plain Mapping of ToolSchema. No craft import — the
    providers -> craft dependency (and therefore the import cycle) stays
    impossible.
    """
    if isinstance(registry, Mapping):
        items: Any = registry.items()
    else:
        specs = getattr(registry, "specs", None)
        if not callable(specs):
            raise TypeError(
                "registry must expose specs() or be a Mapping of ToolSchema"
            )
        items = specs().items()
    schemas: dict[str, ToolSchema] = {}
    for name, spec in items:
        schemas[str(name)] = spec if isinstance(spec, ToolSchema) else _coerce_spec(spec)
    return schemas


def _coerce_spec(spec: Any) -> ToolSchema:
    """Duck-typed ToolSpec-like object -> ToolSchema."""
    name = str(spec.name)
    version = int(spec.version)
    params = tuple(
        ParamSchema(
            name=str(param.name),
            kind=param.kind,
            required=bool(getattr(param, "required", False)),
            max_len=getattr(param, "max_len", None),
            min_value=getattr(param, "min_value", None),
            max_value=getattr(param, "max_value", None),
        )
        for param in getattr(spec, "params", ())
    )
    return ToolSchema(name=name, version=version, params=params)


class ToolCallSelfCheck:
    """Stateful checker: validates envelopes, arms ONE retry, then gives up."""

    def __init__(self, schemas: RegistrySchema) -> None:
        self.schemas: dict[str, ToolSchema] = dict(schemas)
        self.attempts = 0
        self.valid = 0
        self.retried = 0
        self.give_ups = 0
        self.last_outcome: CheckOutcome | None = None
        self._awaiting_retry = False

    @classmethod
    def from_registry(cls, registry: object) -> ToolCallSelfCheck:
        """Build from a craft.tools.ToolRegistry (or any specs()-bearing
        object / Mapping of ToolSchema)."""
        return cls(schemas_from_registry(registry))

    def check(self, envelope: object) -> CheckOutcome:
        """Validate one envelope and update the retry state machine.

        A "retry" outcome arms exactly one retry: the NEXT invalid envelope
        becomes a "give_up" carrying the same stable error code; a valid
        envelope always resets the state.
        """
        self.attempts += 1
        outcome = validate_envelope(self.schemas, envelope)
        self.last_outcome = outcome
        if outcome.status == "valid":
            self.valid += 1
            self._awaiting_retry = False
            return outcome
        if self._awaiting_retry:
            self._awaiting_retry = False
            self.give_ups += 1
            return CheckOutcome(
                status="give_up",
                code=outcome.code,
                message=outcome.message,
                tool=outcome.tool,
                version=outcome.version,
            )
        self._awaiting_retry = True
        self.retried += 1
        return outcome

    def check_with_retry(self, produce: EnvelopeProducer) -> CheckOutcome:
        """Full self-check loop with the injected model callable.

        produce(instruction_or_None) -> raw envelope. The retry instruction
        is passed on the second call only; a second invalid envelope gives
        up with the stable error code. No live LLM — the caller injects the
        model round-trip.
        """
        outcome = self.check(produce(None))
        if outcome.status != "retry":
            return outcome
        return self.check(produce(retry_instruction(outcome)))

    def metrics(self) -> dict[str, Any]:
        """Serializable counters incl. the tool-call success rate."""
        total = self.attempts
        return {
            "attempts": self.attempts,
            "valid": self.valid,
            "retried": self.retried,
            "success": self.valid,
            "give_ups": self.give_ups,
            "tool_call_success_rate": (
                round(self.valid / total, 4) if total else 0.0
            ),
        }


# -- edit-proposal self-check (SpecCraft M2 diagnose-fix) ---------------------


def is_test_file_path(path: str) -> bool:
    """True when a repo-relative path matches a test-file pattern (W112).

    Patterns: anything under "tests/" at any depth (tests/**), or a
    basename matching "test_*.py" / "*_test.py". Backslashes and leading
    "./" are normalized so Windows-style paths match too.
    """
    normalized = path.strip().replace("\\", "/").lstrip("./")
    if normalized == "tests" or normalized.startswith("tests/"):
        return True
    filename = normalized.rsplit("/", 1)[-1]
    if not filename.endswith(".py"):
        return False
    return filename.startswith("test_") or filename.endswith("_test.py")


def validate_edit_proposal(data: object) -> CheckOutcome:
    """Pure edit-proposal validation: top level, edits array, per-op schema.

    Accepts the documented envelope {"diagnosis": str, "edits": [...]} or a
    bare [...] array; every edit op must carry a non-empty repo-relative
    path and an action of exactly "apply_edit" (string old/new) or
    "write_file" (string new). Anything else — including unparseable raw
    text wrapped in a ProposalParseFailure — returns a "retry" outcome with
    the stable code; the stateful EditProposalSelfCheck turns a second
    consecutive retry into "give_up".
    """
    if isinstance(data, ProposalParseFailure):
        return _retry(
            CODE_PROPOSAL_INVALID,
            f"模型输出无法解析为 JSON (尾部: {data.snippet})",
            "",
            0,
        )
    if isinstance(data, list):
        ops: Any = data
    elif isinstance(data, dict):
        raw_ops = data.get("edits")
        if not isinstance(raw_ops, list):
            keys = sorted(str(key) for key in data if isinstance(key, str))[:8]
            detail = ", ".join(keys) if keys else "(空对象)"
            return _retry(
                CODE_PROPOSAL_INVALID,
                f"模型输出缺少 edits 数组 (顶层键: {detail})",
                "",
                0,
            )
        ops = raw_ops
    else:
        return _retry(
            CODE_PROPOSAL_INVALID,
            f"模型输出顶层必须是 JSON 对象或数组 (收到 {type(data).__name__})",
            "",
            0,
        )
    for index, op in enumerate(ops):
        if not isinstance(op, dict):
            return _retry(CODE_PROPOSAL_INVALID, f"edits[{index}] 必须是 JSON 对象", "", 0)
        action = op.get("action")
        path = op.get("path")
        if not isinstance(path, str) or not path.strip():
            return _retry(CODE_PROPOSAL_INVALID, f"edits[{index}] 缺少合法 path", "", 0)
        if is_test_file_path(path):
            return _retry(
                CODE_TEST_FILE_FORBIDDEN,
                f"edits[{index}] 目标 {path.strip()!r} 是测试文件, 禁止创建或修改测试文件 — "
                "隐藏测试由评测框架应用, 请只修复生产/源代码使隐藏测试通过",
                "",
                0,
            )
        if action == "apply_edit":
            if not isinstance(op.get("old"), str) or not isinstance(op.get("new"), str):
                return _retry(
                    CODE_PROPOSAL_INVALID,
                    f"edits[{index}] apply_edit 需要字符串 old/new",
                    "",
                    0,
                )
        elif action == "write_file":
            if not isinstance(op.get("new"), str):
                return _retry(
                    CODE_PROPOSAL_INVALID,
                    f"edits[{index}] write_file 需要字符串 new",
                    "",
                    0,
                )
        else:
            return _retry(
                CODE_PROPOSAL_INVALID,
                f"edits[{index}] 未知动作 {action!r} (仅支持 apply_edit|write_file)",
                "",
                0,
            )
    return CheckOutcome(status="valid", code="", message="", tool="", version=0)


def edit_retry_instruction(outcome: CheckOutcome) -> str:
    """ONE deterministic repair instruction for a rejected edit proposal.

    A test-file rejection (CODE_TEST_FILE_FORBIDDEN) gets a dedicated
    source-only instruction: hidden tests are applied by the harness, so
    the model must re-propose edits to production/source code only.
    """
    if outcome.code == CODE_TEST_FILE_FORBIDDEN:
        return (
            "EDIT PROPOSAL SELF-CHECK — your previous reply was REJECTED and NOT executed.\n"
            f"error code: [{outcome.code}] {outcome.message}\n"
            "Repair rule: test files must never be created or modified — the hidden "
            "FAIL_TO_PASS tests are applied by the harness itself. Respond with exactly "
            'ONE corrected JSON object whose top-level keys are "diagnosis" (string, one '
            'sentence) and "edits" (array of edit operations). Every edit must be a '
            "source-only fix: target production/source code so the hidden tests pass, "
            'e.g. {"diagnosis": "the bug is ...", "edits": [{"action": "apply_edit", '
            '"path": "src/calc.py", "old": "return x / 2", "new": "return x * 2"}]}. '
            'Every edit needs "action" ("apply_edit" with old/new, or "write_file" with '
            'new) and a repo-relative "path" pointing at source code, never a test file. '
            "No markdown fences, no prose — only the JSON object."
        )
    return (
        "EDIT PROPOSAL SELF-CHECK — your previous reply was REJECTED and NOT executed.\n"
        f"error code: [{outcome.code}] {outcome.message}\n"
        "Repair rule: respond with exactly ONE corrected JSON object whose top-level keys "
        'are "diagnosis" (string, one sentence) and "edits" (array of edit operations), e.g. '
        '{"diagnosis": "the bug is ...", "edits": [{"action": "apply_edit", "path": "calc.py", '
        '"old": "return x / 2", "new": "return x * 2"}]}. '
        'Every edit needs "action" ("apply_edit" with old/new, or "write_file" with new) and a '
        'repo-relative "path". No markdown fences, no prose — only the JSON object.'
    )


class EditProposalSelfCheck:
    """Stateful checker for the M2 edit proposal: validates the parsed data,
    arms exactly ONE repair call, then gives up carrying the stable error
    code (same state machine as ToolCallSelfCheck, no live LLM — the model
    round-trip is injected as the producer callable)."""

    def __init__(self) -> None:
        self.attempts = 0
        self.valid = 0
        self.retried = 0
        self.give_ups = 0
        self.last_outcome: CheckOutcome | None = None
        self.last_data: object | None = None
        self._awaiting_retry = False

    def check(self, data: object) -> CheckOutcome:
        """Validate one parsed proposal and update the retry state machine.

        The retry arms exactly one repair: the NEXT invalid proposal becomes
        a "give_up" carrying the same stable error code; a valid proposal
        always resets the state. last_data records the most recent parsed
        payload so callers can consume the validated object.
        """
        self.attempts += 1
        self.last_data = data
        outcome = validate_edit_proposal(data)
        self.last_outcome = outcome
        if outcome.status == "valid":
            self.valid += 1
            self._awaiting_retry = False
            return outcome
        if self._awaiting_retry:
            self._awaiting_retry = False
            self.give_ups += 1
            return CheckOutcome(
                status="give_up",
                code=outcome.code,
                message=outcome.message,
                tool=outcome.tool,
                version=outcome.version,
            )
        self._awaiting_retry = True
        self.retried += 1
        return outcome

    def check_with_retry(self, produce: Callable[[str | None], object]) -> CheckOutcome:
        """Full self-check loop with the injected model callable.

        produce(instruction_or_None) -> parsed proposal data. The repair
        instruction is passed on the second call only; a second invalid
        proposal gives up with the stable error code.
        """
        outcome = self.check(produce(None))
        if outcome.status != "retry":
            return outcome
        return self.check(produce(edit_retry_instruction(outcome)))

    def metrics(self) -> dict[str, Any]:
        """Serializable counters incl. the proposal success rate."""
        total = self.attempts
        return {
            "attempts": self.attempts,
            "valid": self.valid,
            "retried": self.retried,
            "give_ups": self.give_ups,
            "proposal_success_rate": (
                round(self.valid / total, 4) if total else 0.0
            ),
        }
