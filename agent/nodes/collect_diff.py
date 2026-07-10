"""collect_diff node — analyze git diff between base and head."""

import re

from agent.state import Phase0State


def collect_diff_node(state: Phase0State) -> dict:
    """Collect and analyze the git diff between base and head.

    Identifies changed Java symbols (classes, methods).
    """
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    head_ref = state.get("head_ref", "head-v1")

    changed_symbols: list[str] = []

    try:
        # Get list of changed files
        import subprocess
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", base_ref, head_ref],
            capture_output=True, text=True, timeout=30,
        )
        changed_files = [
            f.strip() for f in result.stdout.splitlines() if f.strip()
        ]

        # Get detailed diff for Java files
        java_files = [f for f in changed_files if f.endswith(".java")]
        for jf in java_files:
            diff_result = subprocess.run(
                ["git", "-C", repo_path, "diff", base_ref, head_ref, "--", jf],
                capture_output=True, text=True, timeout=30,
            )
            diff_text = diff_result.stdout

            # Extract changed symbols from diff
            sym_re = re.compile(
                r'[-+]\s*(@\w+.*|public\s+\w+\s+\w+\(|private\s+\w+\s+\w+\()'
            )
            removed = sym_re.findall(
                "\n".join(line for line in diff_text.splitlines() if line.startswith("-"))
            )
            added = sym_re.findall(
                "\n".join(line for line in diff_text.splitlines() if line.startswith("+"))
            )

            for sym in removed:
                changed_symbols.append(f"REMOVED: {sym.strip()} in {jf}")
            for sym in added:
                changed_symbols.append(f"ADDED: {sym.strip()} in {jf}")

            # Also detect annotation removal
            annotations_removed = re.findall(
                r'-\s*(@PreAuthorize|@Transactional|@Secured|@RolesAllowed)\([^)]*\)',
                diff_text,
            )
            for ann in annotations_removed:
                changed_symbols.append(f"ANNOTATION_REMOVED: {ann} in {jf}")

    except Exception as e:
        return {
            "changed_symbols": [f"Error collecting diff: {e}"],
        }

    if not changed_symbols and not changed_files:
        changed_symbols = ["No changes detected between base and head"]

    return {"changed_symbols": changed_symbols}
