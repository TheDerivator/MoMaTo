"""Traceability tooling: reads requirement IDs and finds the tests that name them."""

import re
from pathlib import Path

import pytest

from scripts import trace

REQUIREMENTS_TEXT = """\
### 3.1 Shell (SH)

- **SH-1** Layout.
- **SH-2** Menu.

### 3.2 Projects (PL)

- **PL-1** Header.
  - **PL-9** an indented bullet is a requirement too.

## 4. Rules

### 4.1 Calendar

- Today is the server's date.

### 4.8 Timesheet booking

Some text with **bold** and a [link] that is not an ID.
"""

IDS = ["SH-1", "SH-2", "PL-1", "PL-9", "R4.1", "R4.8"]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ids_are_read_in_document_order() -> None:
    assert trace.requirement_ids(REQUIREMENTS_TEXT) == IDS


def test_tags_must_have_a_known_area_and_stand_in_brackets() -> None:
    text = "proves [SH-1] and [PL-1, R4.8] but not SH-2, [UTF-8], [x] or [ZZ-3]"
    assert trace.tags_in(text, {"SH", "PL", "R4"}) == {"SH-1", "PL-1", "R4.8"}


def test_an_unknown_number_in_a_known_area_is_still_a_tag() -> None:
    """So that a typo such as SH-99 is reported instead of silently ignored."""
    assert trace.tags_in("[SH-99]", {"SH"}) == {"SH-99"}


def test_python_tests_name_ids_in_docstrings_and_names() -> None:
    source = '''
"""Module docs [SH-1]."""

def test_one():
    """Proves [SH-2]."""

def helper():
    """Not a test, but still scanned: [PL-1]."""

class TestGroup:
    """Group [R4.1]."""
    def test_two(self):
        value = "[PL-9] in a string is not a docstring"
'''
    texts = "\n".join(trace.python_texts(source))
    assert trace.tags_in(texts, {"SH", "PL", "R4"}) == {"SH-1", "SH-2", "PL-1", "R4.1"}


def test_js_tests_name_ids_in_test_names_and_the_leading_comment() -> None:
    source = """\
// Unit tests for lib/format.js [SH-1]
import { test } from "node:test";

test("[SH-2] formats", () => {});
describe('[PL-1, PL-9] suite', () => {});
it(`[R4.8] template`, () => {});
const note = "[R4.1] is only data";
"""
    texts = "\n".join(trace.js_texts(source))
    assert trace.tags_in(texts, {"SH", "PL", "R4"}) == {"SH-1", "SH-2", "PL-1", "PL-9", "R4.8"}


def test_collect_tags_lists_the_files_naming_each_tag(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    write(tests / "unit" / "test_a.py", 'def test_a():\n    """[SH-1]"""\n')
    write(tests / "unit" / "test_b.py", 'def test_b():\n    """[SH-1], [SH-2]"""\n')
    write(tests / "js" / "x.test.mjs", 'test("[PL-1] y", () => {});\n')
    write(tests / "unit" / "helpers.py", 'def test_not_collected():\n    """[PL-9]"""\n')
    found = trace.collect_tags(tests, {"SH", "PL"})
    assert found == {
        "SH-1": ["tests/unit/test_a.py", "tests/unit/test_b.py"],
        "SH-2": ["tests/unit/test_b.py"],
        "PL-1": ["tests/js/x.test.mjs"],
    }


def test_measure_reports_untested_and_unknown_ids(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    write(tests / "test_a.py", 'def test_a():\n    """[SH-1] [R4.8] [SH-77]"""\n')
    coverage = trace.measure(REQUIREMENTS_TEXT, tests)
    assert coverage.requirements == IDS
    assert sorted(coverage.tested) == ["R4.8", "SH-1"]
    assert coverage.untested == ["SH-2", "PL-1", "PL-9", "R4.1"]
    assert coverage.unknown == {"SH-77": ["tests/test_a.py"]}


def test_a_selection_restricts_the_report(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    write(tests / "test_a.py", 'def test_a():\n    """[SH-1]"""\n')
    coverage = trace.measure(REQUIREMENTS_TEXT, tests, trace.expand_selection(["SH-1..2", "R4.1"]))
    assert coverage.requirements == ["SH-1", "SH-2", "R4.1"]
    assert coverage.untested == ["SH-2", "R4.1"]


def test_a_selection_naming_a_missing_requirement_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SH-5"):
        trace.measure(REQUIREMENTS_TEXT, tmp_path, {"SH-5"})


def test_ranges_expand() -> None:
    assert trace.expand_selection(["PL-1..3", "SH-6"]) == {"PL-1", "PL-2", "PL-3", "SH-6"}


def test_the_report_lists_every_id_and_counts(tmp_path: Path) -> None:
    write(tmp_path / "tests" / "test_a.py", 'def test_a():\n    """[SH-1]"""\n')
    coverage = trace.measure(REQUIREMENTS_TEXT, tmp_path / "tests")
    report = trace.render(coverage, summary=False)
    for identifier in IDS:
        assert identifier in report
    assert "1 of 6 requirements have a test." in report
    assert "SH-1" in trace.render(coverage, summary=False)
    summary = trace.render(coverage, summary=True)
    assert "PL-9" not in summary
    assert re.search(r"^SH\s+1/2", summary, re.MULTILINE)


def test_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "docs").mkdir()
    write(tmp_path / "docs" / "REQUIREMENTS.md", REQUIREMENTS_TEXT)
    write(tmp_path / "tests" / "test_a.py", 'def test_a():\n    """[SH-1]"""\n')
    monkeypatch.setattr(trace, "REQUIREMENTS", tmp_path / "docs" / "REQUIREMENTS.md")
    monkeypatch.setattr(trace, "TESTS", tmp_path / "tests")

    assert trace.main(["--summary"]) == 0  # report mode never fails on gaps
    assert trace.main(["--strict"]) == 1  # strict mode does
    assert trace.main(["--strict", "--only", "SH-1"]) == 0
    assert trace.main(["--only", "NOPE-1"]) == 2

    write(tmp_path / "tests" / "test_b.py", 'def test_b():\n    """[SH-42]"""\n')
    assert trace.main(["--summary"]) == 1  # a tag naming no requirement is always an error


def test_the_real_requirements_are_all_found() -> None:
    """Every requirement and rule section of docs/REQUIREMENTS.md has an ID the tool can read."""
    text = trace.REQUIREMENTS.read_text(encoding="utf-8")
    ids = trace.requirement_ids(text)
    assert len(ids) == len(set(ids)), "duplicate requirement IDs"
    areas = {trace.prefix_of(i) for i in ids}
    assert areas == {
        "SH", "PL", "PP", "OV", "PG", "PD", "RM", "LB", "DT", "TS", "PPL", "AP", "APP", "AUTH",
        "ADM", "EXP", "TOK", "R4",
    }  # fmt: skip
    for expected in ("SH-1", "SH-12", "PL-8", "TS-15", "PPL-7", "AUTH-5", "TOK-4", "R4.1", "R4.12"):
        assert expected in ids
