"""#335 — CLI help must render cleanly AND every option must be surfaced.

Part of the ``--help`` honesty arc (#294 -> #329 -> #332 -> #334 -> #335):
- #332 proved the *names* a help text mentions are real commands;
- #334 proved every option carries a non-empty ``help=`` string;
- #335 proves two more things that #334 could not:
  1. every registered subcommand's ``--help`` actually **renders** (exit 0, no
     traceback, non-empty output) — a broken decorator / bad default / missing
     import would otherwise make a command's help crash;
  2. every non-hidden option's primary long flag really **appears in that
     command's own ``--help``** — i.e. the help text is not written but hidden
     or mis-attributed to the wrong command.
"""

from __future__ import annotations

import click
from click.testing import CliRunner

from cli.specproof.main import cli


def _walk_commands(cmd: click.Command, path: str = "") -> list[tuple[str, click.Command]]:
    name = path or cmd.name or "?"
    out: list[tuple[str, click.Command]] = [(name, cmd)]
    if isinstance(cmd, click.Group):
        for sub in sorted(cmd.commands.values(), key=lambda c: c.name or ""):
            out.extend(_walk_commands(sub, f"{path} {sub.name}".strip()))
    return out


def _options(cmd: click.Command) -> list[click.Option]:
    return [p for p in cmd.params if isinstance(p, click.Option)]


def _primary_long_flag(opt: click.Option) -> str | None:
    longs = [o for o in opt.opts if o.startswith("--")]
    if longs:
        return longs[0]
    return opt.opts[0] if opt.opts else None


def test_every_subcommand_help_renders_cleanly():
    runner = CliRunner()
    commands = _walk_commands(cli)
    # positive control: the tree must actually contain commands
    assert len(commands) >= 10, f"too few commands walked: {len(commands)}"

    crashes: list[str] = []
    for path, cmd in commands:
        result = runner.invoke(cmd, ["--help"])
        out = result.output or ""
        had_traceback = "Traceback" in out or (
            result.exception is not None
            and not isinstance(result.exception, SystemExit)
        )
        if result.exit_code != 0 or had_traceback or not out.strip():
            crashes.append(
                f"{path}: exit={result.exit_code} tb={had_traceback} len={len(out)}"
            )

    assert not crashes, "these commands render a broken --help:\n" + "\n".join(crashes)


def test_every_non_hidden_option_is_surfaced_in_own_help():
    runner = CliRunner()
    commands = _walk_commands(cli)

    total_options = 0
    missing: list[str] = []
    seen_fix_repo = False

    for path, cmd in commands:
        result = runner.invoke(cmd, ["--help"])
        out = result.output or ""
        for opt in _options(cmd):
            total_options += 1
            if getattr(opt, "hidden", False):
                continue  # intentionally hidden options are allowed to be absent
            if opt.opts and "--repo" in opt.opts and path.split()[:1] == ["fix"]:
                seen_fix_repo = True
            flag = _primary_long_flag(opt)
            if flag is None:
                continue
            if flag not in out:
                missing.append(f"{path} {flag}")

    # positive controls: real volume, and a known option must be present
    assert total_options >= 40, f"too few options walked: {total_options}"
    assert seen_fix_repo, "did not walk fix --repo; tree shape changed"

    assert not missing, (
        "these options are declared but absent from their own --help "
        "(hidden by accident or attached to the wrong command):\n"
        + "\n".join(missing)
    )
