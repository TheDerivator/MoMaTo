"""Display formatting of dates, days and hours (R4.10): en-GB, locale-free, rounding half up."""

from datetime import date
from fractions import Fraction
from math import floor

MONTHS_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_LONG = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAYS_LONG = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

RELATIVE_DAYS_LIMIT = 7


def round_half_up(value: Fraction | int) -> int:
    """Round to the nearest integer, halves upwards (what `Math.round` does in the browser)."""
    return floor(Fraction(value) + Fraction(1, 2))


def format_date(d: date) -> str:
    """`8 Oct 2026`."""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year}"


def format_short_date(d: date) -> str:
    """`8 Oct`."""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}"


def format_month(d: date) -> str:
    """`Nov ’25`."""
    return f"{MONTHS_SHORT[d.month - 1]} ’{d.year % 100:02d}"


def format_long_date(d: date) -> str:
    """`Thursday 8 October 2026` (the top bar)."""
    return f"{WEEKDAYS_LONG[d.weekday()]} {d.day} {MONTHS_LONG[d.month - 1]} {d.year}"


def relative_date(d: date, today: date) -> str:
    """`Today`, `Yesterday`, `n days ago` below a week, else the date."""
    age = (today - d).days
    if age <= 0:
        return "Today"
    if age == 1:
        return "Yesterday"
    if age < RELATIVE_DAYS_LIMIT:
        return f"{age} days ago"
    return format_date(d)


def _decimal(value: Fraction, places: int) -> str:
    """`value` rounded half up to `places` decimals, without trailing zeros."""
    scale = 10**places
    scaled = round_half_up(value * scale)
    whole, fraction = divmod(abs(scaled), scale)
    sign = "-" if scaled < 0 else ""
    if fraction == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{str(fraction).zfill(places).rstrip('0')}"


def format_days(days: Fraction | int) -> str:
    """Days with at most one decimal: `12 d`, `12.5 d`."""
    return f"{_decimal(Fraction(days), 1)} d"


def format_hours(minutes: Fraction | int) -> str:
    """Hours of a number of minutes: whole, else up to two decimals: `8 h`, `1.5 h`, `1.67 h`."""
    return f"{_decimal(Fraction(minutes) / 60, 2)} h"
