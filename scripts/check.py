"""One-command quality gate: lint, format, types, contracts, code map, traceability, all tests.

uv run python scripts/check.py          # everything except browser (e2e) tests
uv run python scripts/check.py --e2e    # also run Playwright browser tests (and axe)
uv run python scripts/check.py --fix    # apply ruff fixes and formatting first

Coverage gates (PLAN.md, test strategy): momato/domain 100 % of branches, momato at least 90 %,
momato/static/js/lib at least 95 % of lines.
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOMAIN_COVERAGE_MIN = 100
PACKAGE_COVERAGE_MIN = 90
JS_LIB_COVERAGE_MIN = 95
JS_LIB = "momato/static/js/lib"


def _tool(name: str) -> str:
    """A console script of this environment (next to the interpreter), else whatever is on PATH."""
    candidates = [Path(sys.executable).parent / name, Path(sys.executable).parent / f"{name}.exe"]
    return next((str(p) for p in candidates if p.exists()), name)


def _steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    py = sys.executable
    steps: list[tuple[str, list[str]]] = []
    if args.fix:
        steps += [
            ("ruff fix", [_tool("ruff"), "check", "--fix", "--exit-zero", "."]),
            ("ruff format", [_tool("ruff"), "format", "."]),
            ("codemap", [py, "scripts/gen_codemap.py"]),
        ]
    marker = "not scale and not visual" if args.e2e else "not e2e and not scale and not visual"
    steps += [
        ("ruff lint", [_tool("ruff"), "check", "."]),
        ("ruff format", [_tool("ruff"), "format", "--check", "."]),
        ("pyright", [_tool("pyright")]),
        ("import contracts", [_tool("lint-imports")]),
        ("codemap fresh", [py, "scripts/gen_codemap.py", "--check"]),
        ("traceability", [py, "scripts/trace.py", "--summary"]),
        (
            "pytest",
            [
                py,
                "-m",
                "pytest",
                "-q",
                "-m",
                marker,
                "--cov=momato",
                "--cov-branch",
                "--cov-report=",
            ],
        ),
        (
            "coverage: domain",
            [
                py,
                "-m",
                "coverage",
                "report",
                "--include=momato/domain/*",
                "--skip-covered",
                f"--fail-under={DOMAIN_COVERAGE_MIN}",
            ],
        ),
        (
            "coverage: package",
            [
                py,
                "-m",
                "coverage",
                "report",
                "--skip-covered",
                f"--fail-under={PACKAGE_COVERAGE_MIN}",
            ],
        ),
    ]
    js_tests = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    if js_tests:
        if shutil.which("node"):
            steps.append(
                (
                    "js unit tests",
                    [
                        "node",
                        "--test",
                        "--experimental-test-coverage",
                        f"--test-coverage-include={JS_LIB}/**/*.js",
                        f"--test-coverage-lines={JS_LIB_COVERAGE_MIN}",
                        *js_tests,
                    ],
                )
            )
        else:
            print("! node not found: skipping JS unit tests")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--e2e", action="store_true", help="include Playwright browser tests")
    parser.add_argument("--fix", action="store_true", help="apply automatic fixes first")
    args = parser.parse_args()

    failures: list[str] = []
    for name, command in _steps(args):
        print(f"\n=== {name}: {' '.join(command)}", flush=True)
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
        status = "ok" if result.returncode == 0 else f"FAILED ({result.returncode})"
        print(f"--- {name}: {status} in {time.perf_counter() - started:.1f}s", flush=True)
        if result.returncode != 0:
            failures.append(name)

    print("\n" + ("All checks passed." if not failures else f"Failed: {', '.join(failures)}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
