# mypy: ignore-errors
# bench fixture-data policy: bench/ trees are executed as isolated task
# repositories and are exempt from repo mypy (same policy as tests/); the
# runner itself (scripts/bench_craft.py) is checked with mypy --strict.
"""Deterministic fix rules for task-07 (explicitly injected via --fix-module).

The fix converges over two loop iterations, mirroring a realistic
implement→test→refine cycle:
  1. naive cache (hits avoid recompute, but nothing ever expires);
  2. cache-aside with TTL (expired entries recompute).
"""

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step

_NAIVE_CACHE = '''\
_CACHE: dict[int, int] = {}


def cached_compute(key: int) -> int:
    if key in _CACHE:
        return _CACHE[key]
    value = compute_expensive(key)
    _CACHE[key] = value
    return value
'''

_TTL_CACHE = '''\
_CACHE: dict[int, tuple[float, int]] = {}
_CACHE_TTL_SECONDS = 0.2


def cached_compute(key: int) -> int:
    now = time.monotonic()
    entry = _CACHE.get(key)
    if entry is not None and now - entry[0] < _CACHE_TTL_SECONDS:
        return entry[1]
    value = compute_expensive(key)
    _CACHE[key] = (now, value)
    return value
'''


def fix_add_cache(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    lines = editor.read_file("svc.py")
    text = "\n".join(line for _, line in lines)
    if "if key in _CACHE:" in text:
        # stage 2: the naive cache exists but nothing expires — add the TTL.
        editor.apply_edit("svc.py", _NAIVE_CACHE, _TTL_CACHE)
    else:
        # stage 1: no cache yet — install the naive cache-aside layer.
        editor.apply_edit(
            "svc.py",
            "def cached_compute(key: int) -> int:\n    return compute_expensive(key)\n",
            _NAIVE_CACHE,
        )
    return ["svc.py"]


FIXES: dict[str, FixFunction] = {"*": fix_add_cache}
