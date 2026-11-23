"""scripts/check.py is the CI gate: it fails on a line over the repo's limit, refuses a ruff the lock doesn't
pin, and CI's test job runs it instead of calling ruff or Test Junkie directly."""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from test_junkie.decorators import Suite, test

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"

_spec = importlib.util.spec_from_file_location("check_script", SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def lint_tree(line: str) -> subprocess.CompletedProcess:
    """check.py --lint on a temp tree holding one module made of `line`."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "module.py").write_text(line + "\n", encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--lint", "--root", tmp], capture_output=True, text=True
        )


def string_line(length: int) -> str:
    line = 'X = "' + "a" * (length - 6) + '"'
    assert len(line) == length
    return line


@Suite()
class CheckScript:
    @test()
    def fails_on_a_line_over_110(self):
        out = lint_tree(string_line(111))
        assert out.returncode == 1, out.stdout + out.stderr
        assert "E501" in out.stdout, out.stdout

    @test()
    def passes_a_100_character_line(self):
        # Fails if the repo's line-length = 110 isn't used (ruff's default is 88).
        out = lint_tree(string_line(100))
        assert out.returncode == 0, out.stdout + out.stderr
        assert "check passed" in out.stdout

    @test()
    def refuses_a_ruff_the_lock_does_not_pin(self):
        assert check.ruff_version_error(check.LOCK) is None, "installed ruff should match requirements.lock"
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp, "requirements.lock")
            lock.write_text("ruff==0.0.1\n", encoding="utf-8")
            error = check.ruff_version_error(lock)
        assert error and "pins ruff 0.0.1" in error, error

    @test()
    def ci_runs_the_script_not_ruff_or_test_junkie(self):
        steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["test"]["steps"]
        runs = [s["run"].strip() for s in steps if "run" in s]
        assert "python scripts/check.py --lint" in runs, runs
        assert "python scripts/check.py --tests" in runs, runs
        direct = [r for r in runs if "ruff" in r or "test_junkie" in r]
        assert not direct, f"CI's test job bypasses scripts/check.py: {direct}"
