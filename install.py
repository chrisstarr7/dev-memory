#!/usr/bin/env python3
"""Install only the runtime Skill; defaults to user-local Codex discovery."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "skills" / "dev-memory" / "scripts"))
from dev_memory import main

if __name__ == "__main__":
    raise SystemExit(main(["install", *sys.argv[1:]]))
