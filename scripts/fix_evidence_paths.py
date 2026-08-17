"""Fix evidence artifacts: remove absolute paths, add bundle digest, rebuild capsule."""
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(PROJECT_ROOT, "artifacts", "p0.5", "511A3276")
BUNDLE_PATH = os.path.join(ARCHIVE, "demo-spring-backend.bundle")
CAPSULE_PATH = os.path.join(ARCHIVE, "capsule.zip")
EP_PATH = os.path.join(ARCHIVE, "evidence-pack.json")
AR_PATH = os.path.join(ARCHIVE, "acceptance-report.json")


def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_abs_paths(obj, path=""):
    issues = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            issues += check_abs_paths(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues += check_abs_paths(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        for prefix in ("C:\\", "C:/", "D:\\", "D:/"):
            if prefix in obj:
                # Allow non-path mentions
                if any(kw in obj.lower() for kw in ["introduced_by_head", "diff_summary"]):
                    continue
                issues.append(f"{path}: {obj[:120]}")
    return issues


def main():
    """Fix evidence artifacts in-place."""
    bundle_hash = compute_sha256(BUNDLE_PATH)
    bundle_digest = f"sha256:{bundle_hash}"
    print(f"Bundle digest: {bundle_digest}")

    portable_env = {
        "java_version": "21.0.11",
        "java_vendor": "Amazon Corretto",
        "maven_version": "3.9.9",
        "os_name": "Windows 11",
        "os_arch": "amd64",
        "tool_versions": {
            "python": "3.12",
            "git": "2.x",
            "maven_wrapper": "3.9.9",
        },
    }

    # 1. Fix evidence-pack.json
    with open(EP_PATH, encoding="utf-8") as f:
        ep = json.load(f)
    ep["env_info"] = portable_env
    ep["capsule"]["demo_repository_bundle_digest"] = bundle_digest
    ep["capsule"]["bundle_digest"] = bundle_digest
    with open(EP_PATH, "w", encoding="utf-8") as f:
        json.dump(ep, f, indent=2, ensure_ascii=False)
    print("evidence-pack.json: FIXED")

    # 2. Fix acceptance-report.json
    with open(AR_PATH, encoding="utf-8") as f:
        ar = json.load(f)
    ar["env_info"] = portable_env
    ar["demo_repository_bundle_digest"] = bundle_digest
    with open(AR_PATH, "w", encoding="utf-8") as f:
        json.dump(ar, f, indent=2, ensure_ascii=False)
    print("acceptance-report.json: FIXED")

    # 3. Fix capsule.zip manifest
    tmp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(CAPSULE_PATH, "r") as zf:
        zf.extractall(tmp_dir)

    manifest_path = os.path.join(tmp_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        mf = json.load(f)

    mf["env_info"] = portable_env
    mf["demo_repository_bundle_digest"] = bundle_digest
    mf.pop("manifest_digest", None)

    # Recompute manifest_digest
    manifest_json = json.dumps(mf, indent=2, sort_keys=True, ensure_ascii=False)
    mf["manifest_digest"] = f"sha256:{hashlib.sha256(manifest_json.encode()).hexdigest()}"

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(mf, f, indent=2, ensure_ascii=False)

    # Rebuild capsule
    new_capsule = CAPSULE_PATH + ".tmp"
    with zipfile.ZipFile(new_capsule, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(tmp_dir):
            for fn in files:
                fp = os.path.join(root, fn)
                arc = os.path.relpath(fp, tmp_dir).replace("\\", "/")
                zf.write(fp, arc)

    new_hash = compute_sha256(new_capsule)
    os.replace(new_capsule, CAPSULE_PATH)

    # Update evidence-pack with new capsule digest
    ep["capsule"]["capsule_zip_digest"] = f"sha256:{new_hash}"
    with open(EP_PATH, "w", encoding="utf-8") as f:
        json.dump(ep, f, indent=2, ensure_ascii=False)

    print("capsule.zip: REBUILT")
    print(f"  new capsule_zip_digest: sha256:{new_hash}")
    print(f"  manifest_digest: {mf['manifest_digest']}")

    # Cleanup
    shutil.rmtree(tmp_dir)

    # Verify no absolute paths
    with open(EP_PATH, encoding="utf-8") as f:
        ep2 = json.load(f)
    with open(AR_PATH, encoding="utf-8") as f:
        ar2 = json.load(f)

    all_ok = True
    for label, data in [
        ("evidence-pack", ep2),
        ("acceptance-report", ar2),
        ("capsule-manifest", mf),
    ]:
        issues = check_abs_paths(data)
        if issues:
            print(f"WARNING: absolute paths in {label}:")
            for i in issues:
                print(f"  {i}")
            all_ok = False
        else:
            print(f"{label}: no absolute paths (OK)")

    if all_ok:
        print("ALL CLEAN")
    else:
        print("SOME ISSUES REMAIN")

    # Print final digest references
    print()
    print("=== Digest References ===")
    print(f"  generated_test_source_digest: {ep2['provenance']['generated_source_digest']}")
    print(f"  evidence_digest:              {ep2['capsule']['evidence_digest']}")
    print(f"  manifest_digest:              {mf['manifest_digest']}")
    print(f"  capsule_zip_digest:           {ep2['capsule']['capsule_zip_digest']}")
    print(f"  demo_repository_bundle_digest: {bundle_digest}")


if __name__ == "__main__":
    main()
