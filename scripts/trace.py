"""Requirement traceability: which IDs of docs/REQUIREMENTS.md have a test that names them.

A test proves a requirement by naming its ID in square brackets: `[TS-7]`, or `[R4.8]` for the
rule section 4.8. Python tests do it in the docstring of a test function, class or module; JS
tests in the name given to `test(...)`, `it(...)` or `describe(...)`, or in the file's leading
comment. Several IDs may share brackets: `[PL-3, PL-4]`.

    uv run python scripts/trace.py                      # every ID, tested or not (exit 0)
    uv run python scripts/trace.py --summary            # counts per area
    uv run python scripts/trace.py --strict             # exit 1 when an ID has no test
    uv run python scripts/trace.py --only PL-1..8 SH-6  # a milestone's list (prefix-n..m ranges)

An ID in a test that REQUIREMENTS.md does not define is always an error (a typo hides a gap).
"""

import argparse
import ast
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "docs" / "REQUIREMENTS.md"
TESTS = ROOT / "tests"

_BULLET_ID = re.compile(r"^\s*- \*\*([A-Z]+-\d+)\*\*", re.MULTILINE)
_RULE_HEADING = re.compile(r"^### 4\.(\d+)\b", re.MULTILINE)
_BRACKETS = re.compile(r"\[([^\[\]]+)\]")
_ID = re.compile(r"([A-Z]+)-(\d+)|(R4)\.(\d+)")
_JS_NAME = re.compile(
    r"""\b(?:test|it|describe)(?:\.\w+)?\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`)"""
)
_RANGE = re.compile(r"([A-Z]+)-(\d+)\.\.(\d+)")


def requirement_ids(text: str) -> list[str]:
    """Every requirement and rule ID of the requirements document, in document order."""
    found = [(m.start(), m.group(1)) for m in _BULLET_ID.finditer(text)]
    found += [(m.start(), f"R4.{m.group(1)}") for m in _RULE_HEADING.finditer(text)]
    return [identifier for _, identifier in sorted(found)]


def tags_in(text: str, prefixes: Iterable[str]) -> set[str]:
    """The IDs named in square brackets in `text`; only IDs whose area prefix is a known one."""
    known = set(prefixes)
    tags: set[str] = set()
    for group in _BRACKETS.findall(text):
        for part in group.split(","):
            match = _ID.fullmatch(part.strip())
            if match and (match.group(1) or match.group(3)) in known:
                tags.add(part.strip())
    return tags


def prefix_of(identifier: str) -> str:
    return identifier.split("-")[0] if "-" in identifier else identifier.split(".")[0]


def python_texts(source: str) -> list[str]:
    """The docstrings of a module's tests (functions, classes, the module) and their names."""
    tree = ast.parse(source)
    texts = [ast.get_docstring(tree) or ""]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            texts.append(ast.get_docstring(node) or "")
            texts.append(node.name)
    return texts


def js_texts(source: str) -> list[str]:
    """The names of a JS test file's tests and suites, and its leading comment block."""
    texts = ["".join(g or "" for g in m.groups()) for m in _JS_NAME.finditer(source)]
    leading: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            leading.append(stripped)
        elif stripped:
            break
    return [*texts, "\n".join(leading)]


def collect_tags(tests_dir: Path, prefixes: Iterable[str]) -> dict[str, list[str]]:
    """Tag → the test files naming it (paths relative to the tests folder's parent, sorted)."""
    prefixes = set(prefixes)
    found: dict[str, set[str]] = {}
    files = [*sorted(tests_dir.rglob("test_*.py")), *sorted(tests_dir.rglob("*.test.mjs"))]
    for path in files:
        source = path.read_text(encoding="utf-8")
        texts = python_texts(source) if path.suffix == ".py" else js_texts(source)
        relative = path.relative_to(tests_dir.parent).as_posix()
        for tag in tags_in("\n".join(texts), prefixes):
            found.setdefault(tag, set()).add(relative)
    return {tag: sorted(paths) for tag, paths in found.items()}


def expand_selection(items: Sequence[str]) -> set[str]:
    """`PL-1..8` becomes PL-1 … PL-8; anything else is taken as it is."""
    selected: set[str] = set()
    for item in items:
        match = _RANGE.fullmatch(item)
        if match:
            area, first, last = match.group(1), int(match.group(2)), int(match.group(3))
            selected |= {f"{area}-{n}" for n in range(first, last + 1)}
        else:
            selected.add(item)
    return selected


@dataclass(frozen=True)
class Coverage:
    requirements: list[str]
    tested: dict[str, list[str]]  # requirement → test files
    unknown: dict[str, list[str]]  # tag in a test that REQUIREMENTS.md doesn't define → files

    @property
    def untested(self) -> list[str]:
        return [r for r in self.requirements if r not in self.tested]


def measure(requirements_text: str, tests_dir: Path, only: set[str] | None = None) -> Coverage:
    ids = requirement_ids(requirements_text)
    if only and (missing := sorted(only - set(ids))):
        raise ValueError(f"not requirement IDs: {', '.join(missing)}")
    tags = collect_tags(tests_dir, {prefix_of(i) for i in ids})
    unknown = {tag: files for tag, files in tags.items() if tag not in ids}
    selected = [i for i in ids if only is None or i in only]
    return Coverage(selected, {i: tags[i] for i in selected if i in tags}, unknown)


def _by_area(identifiers: Iterable[str]) -> dict[str, list[str]]:
    areas: dict[str, list[str]] = {}
    for identifier in identifiers:
        areas.setdefault(prefix_of(identifier), []).append(identifier)
    return areas


def render(coverage: Coverage, *, summary: bool) -> str:
    lines: list[str] = []
    for area, identifiers in _by_area(coverage.requirements).items():
        done = sum(1 for i in identifiers if i in coverage.tested)
        lines.append(f"{area:<5} {done:>3}/{len(identifiers):<3}")
        if not summary:
            for identifier in identifiers:
                files = coverage.tested.get(identifier)
                lines.append(
                    f"  ok  {identifier:<8} {', '.join(files)}" if files else f"  --  {identifier}"
                )
    total = len(coverage.requirements)
    lines.append(f"\n{total - len(coverage.untested)} of {total} requirements have a test.")
    for tag, files in coverage.unknown.items():
        lines.append(f"unknown ID [{tag}] in {', '.join(files)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--strict", action="store_true", help="exit 1 when an ID has no test")
    parser.add_argument("--summary", action="store_true", help="counts per area only")
    parser.add_argument("--only", nargs="+", metavar="ID", help="IDs or PREFIX-n..m ranges")
    args = parser.parse_args(argv)

    only = expand_selection(args.only) if args.only else None
    try:
        coverage = measure(REQUIREMENTS.read_text(encoding="utf-8"), TESTS, only)
    except ValueError as error:
        print(error)
        return 2
    print(render(coverage, summary=args.summary))
    if coverage.unknown:
        return 1
    return 1 if args.strict and coverage.untested else 0


if __name__ == "__main__":
    sys.exit(main())
