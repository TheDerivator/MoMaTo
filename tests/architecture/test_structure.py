"""Layer contracts hold, the code map is fresh, files describe themselves, app.py stays thin."""

import importlib.util
import shutil
import subprocess
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
from importlinter.cli import lint_imports

import momato

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_contracts_hold() -> None:
    """The contracts live in pyproject.toml ([tool.importlinter])."""
    assert lint_imports(config_filename=str(ROOT / "pyproject.toml"), no_cache=True) == 0


def test_codemap_is_up_to_date() -> None:
    codemap = _load_script("gen_codemap")
    current = (ROOT / "docs" / "CODEMAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == codemap.render(), "run `uv run python scripts/gen_codemap.py`"


def test_every_source_file_has_a_summary() -> None:
    """The code map is only useful if every file describes itself (vendored code excepted)."""
    codemap = _load_script("gen_codemap")
    missing = [
        str(path.relative_to(ROOT))
        for folder in ("momato", "tests", "scripts")
        for pattern in ("*.py", "*.js", "*.mjs", "*.css", "*.html")
        for path in (ROOT / folder).rglob(pattern)
        if not {"__pycache__", "vendor"} & set(path.parts) and not codemap.summarize(path)
    ]
    assert missing == []


def test_no_source_file_is_hidden_by_gitignore() -> None:
    """A generic rule such as `lib/` once hid the whole `static/js/lib` folder from the
    repository, so the deployed copy could not load. Ignored files may only be caches."""
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    listing = subprocess.run(  # noqa: S603  (fixed arguments)
        [git, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    hidden = [
        name
        for name in listing.split("\0")
        if name.startswith(("momato/", "tests/", "scripts/"))
        and "__pycache__" not in name
        and not name.startswith("tests/e2e/_failures/")
    ]
    assert hidden == [], "ignored by .gitignore, so never committed: tighten the rule"


def test_entrypoint_stays_thin() -> None:
    code_lines = [
        line
        for line in (ROOT / "app.py").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", '"""'))
    ]
    assert len(code_lines) <= 3, "app.py only wires the app: put logic in the momato package"


def test_every_layer_of_the_contract_exists_as_a_package() -> None:
    """A layer named in the contract but missing on disk would silently weaken it."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    layers: list[str] = config["tool"]["importlinter"]["contracts"][0]["layers"]
    for layer in layers:
        name = layer.removeprefix("momato.")
        assert (ROOT / "momato" / name).is_dir() or (ROOT / "momato" / f"{name}.py").is_file()


def test_the_package_version_matches_pyproject() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert momato.__version__ == config["project"]["version"]
