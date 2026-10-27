#!/usr/bin/env python3
"""Build a whitelist-only ZIP without including any running memory data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "skills" / "dev-memory" / "scripts"))
from dev_memory import RELEASE_FILES  # noqa: E402

def build(target: Path) -> dict:
    target = target.expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.parent.resolve() / target.name
    if target.is_relative_to(ROOT.resolve()):
        raise ValueError("Release output cannot be written inside the source package.")
    entries = []
    for name in RELEASE_FILES:
        source = ROOT / name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(f"Missing, non-file, or escaped release path: {name}")
        data = source.read_bytes()
        entries.append((name, data, hashlib.sha256(data).hexdigest()))
    if (ROOT / "LICENSE").read_bytes() != (ROOT / "skills/dev-memory/LICENSE").read_bytes():
        raise ValueError("Repository and runtime Skill licenses must agree.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".dev-memory-release-", dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            manifest = {"package": "dev-memory", "version": "0.9.0", "license_status": "MIT",
                        "files": [{"path": name, "sha256": digest} for name, _, digest in entries]}
            for name, data, _ in entries:
                info = zipfile.ZipInfo(f"dev-memory/{name}", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o100700 if (name.endswith("/dev-memory") or name == "bin/install.cjs") else 0o100600
                info.external_attr = mode << 16
                archive.writestr(info, data)
            info = zipfile.ZipInfo("dev-memory/manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return {"status": "built", "path": str(target), "files": len(entries) + 1,
            "redistribution_ready": True, "license": "MIT"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
