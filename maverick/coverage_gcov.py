"""Open-source structural coverage adapter: gcc --coverage + gcov + gcovr.

Measures statement (line), branch and function coverage of generated C units
under a generated unit-test driver, and returns the dict expected by
SafetySupervisor.promote(..., "H4", coverage=...).

MC/DC is NOT measured by this adapter. GCC < 14 has no condition coverage.
For MC/DC use LLVM >= 18 (clang -fcoverage-mcdc) or GCC >= 14
(-fcondition-coverage); until then the "mcdc" key is reported as None, so any
ASIL D unit fails H4 with an explicit Cov:mcdc reason rather than passing silently.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def measure(sources: list[Path], test_driver: Path, work_dir: Path, timeout_s: int = 60) -> dict:
    work_dir = Path(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    for src in [*sources, test_driver]:
        shutil.copy(src, work_dir / Path(src).name)

    exe = work_dir / "unit_test.exe"
    compile_cmd = ["gcc", "--coverage", "-O0", "-std=c99", "-Wall",
                   *[Path(s).name for s in sources], Path(test_driver).name, "-o", exe.name]
    build = subprocess.run(compile_cmd, cwd=work_dir, capture_output=True, text=True)
    result = {"compiled": build.returncode == 0, "compile_log": build.stderr[-4000:],
              "tests_passed": False, "statement": 0.0, "branch": 0.0, "function": 0.0,
              "mcdc": None, "tool": "gcc+gcov+gcovr"}
    if build.returncode != 0:
        return result

    try:
        run = subprocess.run([str(exe)], cwd=work_dir, capture_output=True, text=True, timeout=timeout_s)
        result["tests_passed"] = run.returncode == 0
        result["test_log"] = (run.stdout + run.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        result["test_log"] = "timeout"
        return result

    summary = subprocess.run(
        [sys.executable, "-m", "gcovr", "--root", ".", "--exclude", Path(test_driver).name,
         "--json-summary", "-"],
        cwd=work_dir, capture_output=True, text=True)
    if summary.returncode != 0:
        result["gcovr_log"] = summary.stderr[-4000:]
        return result
    data = json.loads(summary.stdout)
    result["statement"] = data.get("line_percent", 0.0) / 100.0
    result["branch"] = data.get("branch_percent", 0.0) / 100.0
    result["function"] = data.get("function_percent", 0.0) / 100.0
    return result
