"""Run the CI gate, the one way: python scripts/check.py [--lint | --tests].

The gate is ``ruff check .``, ``ruff format --check .`` (with the ruff pinned in requirements.lock and the
repo's ``[tool.ruff]`` settings), then every Test Junkie suite under ``tests/``. CI's test job runs this
script, so a pass here is the same verdict as CI's for those steps. It stops at the first failing step and
exits with its code. ``--lint`` runs only the two ruff steps (seconds); ``--tests`` only the suites. The
suites run on SQLite, and on Postgres too only when ``TJ_TCMS_TEST_POSTGRES_URL`` is set (CI sets it), so a
local pass without it does not cover Postgres.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements.lock"
CONFIG = ROOT / "pyproject.toml"


def ruff_version_error(lock: Path) -> str | None:
    """Why the installed ruff can't give CI's verdict (not the version `lock` pins), or None when it can."""
    pinned = re.search(r"^ruff==(\S+)", lock.read_text(encoding="utf-8"), re.MULTILINE)
    if not pinned:
        return f"{lock.name} pins no ruff"
    out = subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True, text=True)
    installed = out.stdout.split()[-1] if out.returncode == 0 and out.stdout.split() else None
    if installed != pinned.group(1):
        return (
            f"ruff {installed or 'is not installed'}, but {lock.name} pins ruff {pinned.group(1)}: "
            f"pip install -r {lock.name}"
        )
    return None


def step(label: str, command: list[str], root: Path, env: dict[str, str] | None = None) -> int:
    print(f"== {label}: {' '.join(command)}", flush=True)
    code = subprocess.run(command, cwd=root, env=env).returncode
    if code:
        print(f"== {label} FAILED (exit {code})", flush=True)
    return code


def lint(root: Path) -> int:
    error = ruff_version_error(LOCK)
    if error:
        print(f"== lint FAILED: {error}", flush=True)
        return 1
    ruff = [sys.executable, "-m", "ruff"]
    config = ["--config", str(CONFIG)]
    return step("lint", [*ruff, "check", *config, "."], root) or step(
        "format", [*ruff, "format", "--check", *config, "."], root
    )


def tests(root: Path) -> int:
    # The suites import tests.support; the test_junkie CLI does not put the project root on sys.path.
    path = os.pathsep.join(filter(None, [str(root), os.environ.get("PYTHONPATH")]))
    env = {**os.environ, "PYTHONPATH": path}
    # Test Junkie exits non-zero on any failed, errored or ignored test.
    return step("tests", [sys.executable, "-m", "test_junkie", "run", "-s", "tests"], root, env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    only = parser.add_mutually_exclusive_group()
    only.add_argument("--lint", action="store_true", help="run only ruff check and ruff format --check")
    only.add_argument(
        "--tests",
        action="store_true",
        help="run only the Test Junkie suites (Postgres too only if TJ_TCMS_TEST_POSTGRES_URL is set)",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="tree to check (default: this repo)")
    args = parser.parse_args(argv)
    code = 0 if args.tests else lint(args.root)
    if not code and not args.lint:
        code = tests(args.root)
    if not code:
        print("== check passed", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
