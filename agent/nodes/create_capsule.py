"""create_capsule node — package Bug Capsules for BLOCKER/MAJOR findings."""

import json
import os
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from agent.state import Phase0State


def create_capsule_node(state: Phase0State) -> dict:
    """Create Bug Capsule zip files for each confirmed finding.

    Each capsule contains manifest, requirement, contract, finding,
    generated tests, fixtures, and a run.sh script.
    """
    confirmed_findings = state.get("confirmed_findings", [])
    contracts = state.get("contracts", [])
    requirement_text = state.get("requirement_text", "")
    generated_tests_path = state.get("generated_tests_path", "")
    capsules: list[str] = []

    output_dir = Path("capsules")
    output_dir.mkdir(parents=True, exist_ok=True)

    for finding in confirmed_findings:
        if finding.get("severity") not in ("BLOCKER", "MAJOR"):
            continue

        fid = finding.get("id", str(uuid.uuid4())[:8])
        capsule_dir = output_dir / f"capsule-{fid}"
        capsule_dir.mkdir(parents=True, exist_ok=True)

        # manifest.json
        manifest = {
            "finding_id": fid,
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "created_at": datetime.now(UTC).isoformat(),
            "contract_id": finding.get("contract_id"),
            "evidence_type": finding.get("evidence_type"),
        }
        (capsule_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # requirement.json
        (capsule_dir / "requirement.json").write_text(
            json.dumps({"text": requirement_text}, indent=2), encoding="utf-8"
        )

        # contract.json
        matching = [c for c in contracts if c.get("id") == finding.get("contract_id")]
        (capsule_dir / "contract.json").write_text(
            json.dumps(matching[0] if matching else {}, indent=2), encoding="utf-8"
        )

        # finding.json
        (capsule_dir / "finding.json").write_text(
            json.dumps(finding, indent=2), encoding="utf-8"
        )

        # generated-tests/
        tests_dir = capsule_dir / "generated-tests"
        tests_dir.mkdir(exist_ok=True)
        if generated_tests_path and os.path.exists(generated_tests_path):
            dest = tests_dir / Path(generated_tests_path).name
            dest.write_text(Path(generated_tests_path).read_text(encoding="utf-8"))

        # fixtures/
        fixtures_dir = capsule_dir / "fixtures"
        fixtures_dir.mkdir(exist_ok=True)
        (fixtures_dir / "base-ref.txt").write_text(state.get("base_ref", ""))
        (fixtures_dir / "head-ref.txt").write_text(state.get("head_ref", ""))

        # environment/
        env_dir = capsule_dir / "environment"
        env_dir.mkdir(exist_ok=True)
        (env_dir / ".env.template").write_text(
            "LLM_API_KEY=replace_me\n"
            "MYSQL_PASSWORD=replace_me\n"
            "REDIS_PASSWORD=replace_me\n"
        )

        # run.sh
        run_script = (
            "#!/bin/bash\n"
            "set -e\n"
            'echo "SpecProof Bug Capsule Replay"\n'
            f'echo "Finding: {fid}"\n'
            f'echo "Severity: {finding.get("severity")}"\n'
            'echo ""\n'
            'echo "To replay this finding:"\n'
            f'echo "  cd {capsule_dir}"\n'
            'echo "  specproof verify --repo <repo> --base <base>"\n'
            'echo "  --head <head> --spec requirement.json"\n'
        )
        run_path = capsule_dir / "run.sh"
        run_path.write_text(run_script, encoding="utf-8")

        # README.md
        readme = (
            f"# Bug Capsule: {fid}\n\n"
            f"**Severity:** {finding.get('severity')}\n"
            f"**Confidence:** {finding.get('confidence')}\n\n"
            f"## Finding\n{finding.get('description', 'No description')}\n\n"
            f"## Replay\n```bash\ncd {capsule_dir} && bash run.sh\n```\n"
        )
        (capsule_dir / "README.md").write_text(readme, encoding="utf-8")

        # Package as zip
        zip_path = output_dir / f"capsule-{fid}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in capsule_dir.rglob("*"):
                arcname = file_path.relative_to(capsule_dir)
                zf.write(file_path, arcname)

        capsules.append(str(zip_path.resolve()))

    return {"capsules": capsules}
