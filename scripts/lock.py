"""Make requirements.lock, the one way: python scripts/lock.py [--check].

uv resolves one lock for every platform (``--universal``), so a pin that only some platforms need (uvloop off
Windows, pywin32 on it) keeps its environment marker. The current lock is read as preferences, so no pin moves
unless pyproject.toml asks for it. ``--check`` compiles into a temp copy and exits 1 if the lock is stale.
"""

import argparse
import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements.lock"
COMMAND = "python scripts/lock.py"


def compile_to(output: Path) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "uv", "pip", "compile", "pyproject.toml",
            "--extra", "dev",
            "--universal",
            "--python-version", "3.11",
            "--no-annotate",
            "--quiet",
            "--custom-compile-command", COMMAND,
            "-o", str(output),
        ],
        cwd=ROOT,
        check=True,
    )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if requirements.lock is stale")
    args = parser.parse_args(argv)
    if not args.check:
        compile_to(LOCK)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / LOCK.name
        shutil.copyfile(LOCK, fresh)
        compile_to(fresh)
        old = LOCK.read_text(encoding="utf-8").splitlines(keepends=True)
        new = fresh.read_text(encoding="utf-8").splitlines(keepends=True)
    if old == new:
        print("requirements.lock is up to date")
        return 0
    sys.stdout.writelines(difflib.unified_diff(old, new, "requirements.lock", "fresh"))
    print(f"\nrequirements.lock is stale: run {COMMAND}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
