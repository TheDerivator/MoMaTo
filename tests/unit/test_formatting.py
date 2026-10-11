"""Display formatting of dates, days and hours. [R4.10]"""

from datetime import date
from fractions import Fraction

import pytest

from momato.domain import formatting as f
from tests.helpers import load_fixture

TABLE = load_fixture("formatting")


@pytest.mark.parametrize(("iso", "text"), TABLE["date"])
def test_dates(iso: str, text: str) -> None:
    assert f.format_date(date.fromisoformat(iso)) == text


@pytest.mark.parametrize(("iso", "text"), TABLE["short_date"])
def test_short_dates(iso: str, text: str) -> None:
    assert f.format_short_date(date.fromisoformat(iso)) == text


@pytest.mark.parametrize(("iso", "text"), TABLE["month"])
def test_months(iso: str, text: str) -> None:
    assert f.format_month(date.fromisoformat(iso)) == text


@pytest.mark.parametrize(("iso", "text"), TABLE["long_date"])
def test_long_dates(iso: str, text: str) -> None:
    assert f.format_long_date(date.fromisoformat(iso)) == text


@pytest.mark.parametrize("case", TABLE["relative"], ids=lambda c: c["text"])
def test_relative_dates(case: dict[str, str]) -> None:
    result = f.relative_date(date.fromisoformat(case["date"]), date.fromisoformat(case["today"]))
    assert result == case["text"]


@pytest.mark.parametrize(("value", "text"), TABLE["days"])
def test_days_have_at_most_one_decimal(value: str, text: str) -> None:
    assert f.format_days(Fraction(value)) == text


@pytest.mark.parametrize(("minutes", "text"), TABLE["hours"])
def test_hours_are_whole_or_have_up_to_two_decimals(minutes: int, text: str) -> None:
    assert f.format_hours(minutes) == text


def test_rounding_goes_half_up_even_for_negative_halves() -> None:
    assert f.round_half_up(Fraction(5, 2)) == 3
    assert f.round_half_up(Fraction(-5, 2)) == -2  # what Math.round does
    assert f.round_half_up(2) == 2


def test_negative_amounts_keep_their_sign() -> None:
    assert f.format_days(Fraction(-5, 2)) == "-2.5 d"
    assert f.format_hours(-90) == "-1.5 h"
