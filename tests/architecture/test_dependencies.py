"""Dependency groups (D-003): nothing for tests or tooling reaches a production install."""

import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Test and tooling packages: they belong in the `dev` group, never in a `uv sync --no-dev` install.
TOOLING = {
    "axe-playwright-python",
    "coverage",
    "httpx",
    "httpx2",
    "hypothesis",
    "import-linter",
    "openpyxl",
    "pillow",
    "playwright",
    "pyright",
    "pytest",
    "pytest-cov",
    "pytest-playwright",
    "ruff",
}
# What the dev group must hold (the plan's M0 list); later milestones add theirs.
REQUIRED_DEV = {
    "axe-playwright-python",
    "httpx2",
    "hypothesis",
    "import-linter",
    "pyright",
    "pytest",
    "pytest-cov",
    "pytest-playwright",
    "ruff",
}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    assert match, requirement
    return _normalize(match.group())


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _lock_packages() -> dict[str, dict[str, Any]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {_normalize(p["name"]): p for p in lock["package"]}


def _runtime_closure(roots: list[dict[str, Any]], packages: dict[str, dict[str, Any]]) -> set[str]:
    """Every package installed for the given root requirements, following extras."""
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        requirement = pending.pop()
        name = _normalize(requirement["name"])
        if name in seen and not requirement.get("extra"):
            continue
        package = packages[name]
        if name not in seen:
            seen.add(name)
            pending.extend(package.get("dependencies", []))
        for extra in requirement.get("extra", []):
            pending.extend(package.get("optional-dependencies", {}).get(extra, []))
    return seen


def test_no_test_or_tooling_package_is_a_runtime_dependency() -> None:
    declared = {_requirement_name(r) for r in _pyproject()["project"]["dependencies"]}
    assert declared & TOOLING == set()


def test_the_lock_file_installs_no_tooling_in_production() -> None:
    """`uv sync --no-dev` follows momato's dependencies and their extras through uv.lock."""
    packages = _lock_packages()
    project = packages["momato"]
    closure = _runtime_closure(project["dependencies"], packages)
    assert closure & TOOLING == set()


def test_the_dev_group_holds_the_test_and_tooling_packages() -> None:
    dev = {_requirement_name(r) for r in _pyproject()["dependency-groups"]["dev"]}
    assert dev >= REQUIRED_DEV


def test_the_mssql_driver_is_an_optional_extra() -> None:
    config = _pyproject()
    extras = config["project"]["optional-dependencies"]
    assert {_requirement_name(r) for r in extras["mssql"]} == {"pyodbc"}
    declared = {_requirement_name(r) for r in config["project"]["dependencies"]}
    assert "pyodbc" not in declared
    closure = _runtime_closure(_lock_packages()["momato"]["dependencies"], _lock_packages())
    assert "pyodbc" not in closure
