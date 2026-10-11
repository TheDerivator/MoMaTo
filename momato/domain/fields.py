"""The deployment profile's model and the validation of detail values (DT-2, D-009, D-034, §7).

A profile is plain data: detail cards and fields, the time categories, the task template and a few
numbers. `Profile.from_mapping` builds one from parsed TOML and names the problem when it is
broken (the server then refuses to start); `validate_value` checks a detail value against its
field's type, so the database can keep values generically as JSON.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from fractions import Fraction
from typing import Any

from momato.domain.projects import DEFAULT_HIDDEN_STATUSES, ProjectStatus
from momato.domain.tasks import TemplateTask

KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
CORE_FIELDS = ("number", "department", "priority")  # core project fields a card may show

MAX_TEXT = 300
MAX_LONG_TEXT = 10_000
MAX_TAGS = 20
MAX_TAG = 50


class ProfileError(ValueError):
    """The profile is broken; the message names the card, field or setting at fault."""


class FieldValueError(ValueError):
    """A detail value does not fit its field."""


class FieldType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    NUMBER = "number"
    DATE = "date"
    CHOICE = "choice"
    TAGS = "tags"
    PERSON = "person"
    PROJECT = "project"
    YES_NO = "yes_no"


class CategoryKind(StrEnum):
    OTHER_WORK = "other_work"
    TIME_OFF = "time_off"


@dataclass(frozen=True)
class FieldDef:
    """A card row: a core project field (`core`) or a detail field (`type`)."""

    key: str
    label: str
    type: FieldType | None = None
    core: str | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Card:
    key: str
    title: str
    fields: tuple[FieldDef, ...]


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    kind: CategoryKind


@dataclass(frozen=True)
class Numbers:
    hours_per_day: int = 8
    day_cap_minutes: int = 600
    timesheet_step_minutes: int = 60
    available_days_per_year: int = 220
    other_work_share: Fraction = Fraction(1, 10)
    first_project_number: int = 1000


@dataclass(frozen=True)
class Profile:
    name: str
    cards: tuple[Card, ...]
    categories: tuple[Category, ...]
    task_template: tuple[TemplateTask, ...]
    hidden_statuses: tuple[ProjectStatus, ...] = DEFAULT_HIDDEN_STATUSES
    numbers: Numbers = field(default_factory=Numbers)

    @property
    def detail_fields(self) -> dict[str, FieldDef]:
        """Every detail field by key (core rows excluded)."""
        return {f.key: f for card in self.cards for f in card.fields if f.core is None}

    def categories_of(self, kind: CategoryKind) -> tuple[Category, ...]:
        return tuple(c for c in self.categories if c.kind is kind)

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, Any]) -> Profile:
        """Build a profile from parsed TOML, raising `ProfileError` with a precise message."""
        return _Parser(name).parse(data)


# ---------------------------------------------------------------- parsing


class _Parser:
    def __init__(self, name: str) -> None:
        self.name = name

    def fail(self, where: str, problem: str) -> ProfileError:
        return ProfileError(f"profile {self.name!r}: {where}: {problem}")

    def parse(self, data: Mapping[str, Any]) -> Profile:
        known = {"numbers", "hidden_statuses", "cards", "categories", "task_template"}
        if unknown := sorted(set(data) - known):
            raise self.fail("top level", f"unknown setting {unknown[0]!r}")
        return Profile(
            name=self.name,
            cards=self._cards(data.get("cards", [])),
            categories=self._categories(data.get("categories", [])),
            task_template=self._template(data.get("task_template", [])),
            hidden_statuses=self._hidden(data.get("hidden_statuses", ["stopped"])),
            numbers=self._numbers(data.get("numbers", {})),
        )

    def _key(self, where: str, value: object) -> str:
        if not isinstance(value, str) or not KEY_PATTERN.fullmatch(value):
            raise self.fail(where, f"key {value!r} must be lowercase letters, digits and _")
        return value

    def _text(self, where: str, table: Mapping[str, Any], name: str) -> str:
        value = table.get(name)
        if not isinstance(value, str) or not value.strip():
            raise self.fail(where, f"{name} is required")
        return value.strip()

    def _tables(self, where: str, value: object) -> list[Mapping[str, Any]]:
        if not isinstance(value, list) or not all(isinstance(t, dict) for t in value):  # pyright: ignore[reportUnknownVariableType]
            raise self.fail(where, "must be a list of tables")
        return value  # pyright: ignore[reportUnknownVariableType]

    def _cards(self, raw: object) -> tuple[Card, ...]:
        cards: list[Card] = []
        seen_cards: set[str] = set()
        seen_fields: set[str] = set()
        seen_core: set[str] = set()
        for table in self._tables("cards", raw):
            key = self._key("cards", table.get("key"))
            where = f"card {key!r}"
            if key in seen_cards:
                raise self.fail(where, "duplicate card key")
            seen_cards.add(key)
            fields = tuple(
                self._field(where, t, seen_fields, seen_core)
                for t in self._tables(f"{where} fields", table.get("fields", []))
            )
            cards.append(Card(key, self._text(where, table, "title"), fields))
        return tuple(cards)

    def _field(
        self, card: str, table: Mapping[str, Any], seen: set[str], seen_core: set[str]
    ) -> FieldDef:
        key = self._key(f"{card}: field", table.get("key"))
        where = f"{card}: field {key!r}"
        if key in seen:
            raise self.fail(where, "duplicate field key")
        seen.add(key)
        label = self._text(where, table, "label")
        core, kind = table.get("core"), table.get("type")
        if (core is None) == (kind is None):
            raise self.fail(where, "give exactly one of core and type")
        if core is not None:
            if core not in CORE_FIELDS:
                raise self.fail(where, f"unknown core field {core!r} (use one of: {CORE_FIELDS})")
            if core in seen_core:
                raise self.fail(where, f"core field {core!r} is shown twice")
            seen_core.add(core)
            return FieldDef(key, label, core=core)
        if key in CORE_FIELDS:
            raise self.fail(where, "a detail field cannot be named like a core field")
        try:
            field_type = FieldType(kind)
        except ValueError:
            raise self.fail(
                where,
                f"unknown type {kind!r} (use one of: {', '.join(t.value for t in FieldType)})",
            ) from None
        choices = table.get("choices", [])
        if field_type is FieldType.CHOICE:
            if not isinstance(choices, list) or not choices:
                raise self.fail(where, "a choice field needs a non-empty list of choices")
            if not all(isinstance(c, str) and c.strip() for c in choices):  # pyright: ignore[reportUnknownVariableType]
                raise self.fail(where, "choices must be non-empty text")
            if len(set(choices)) != len(choices):  # pyright: ignore[reportUnknownArgumentType]
                raise self.fail(where, "duplicate choices")
            return FieldDef(key, label, field_type, choices=tuple(choices))  # pyright: ignore[reportUnknownArgumentType]
        if choices:
            raise self.fail(where, "only a choice field has choices")
        return FieldDef(key, label, field_type)

    def _categories(self, raw: object) -> tuple[Category, ...]:
        categories: list[Category] = []
        seen: set[str] = set()
        for table in self._tables("categories", raw):
            key = self._key("categories", table.get("key"))
            where = f"category {key!r}"
            if key in seen:
                raise self.fail(where, "duplicate category key")
            seen.add(key)
            kind = table.get("kind")
            try:
                category_kind = CategoryKind(kind)
            except ValueError:
                raise self.fail(
                    where,
                    f"kind is required, one of: {', '.join(k.value for k in CategoryKind)}",
                ) from None
            categories.append(Category(key, self._text(where, table, "label"), category_kind))
        for kind_needed in CategoryKind:
            if not any(c.kind is kind_needed for c in categories):
                raise self.fail("categories", f"needs at least one of kind {kind_needed.value!r}")
        return tuple(categories)

    def _template(self, raw: object) -> tuple[TemplateTask, ...]:
        tasks: list[TemplateTask] = []
        for index, table in enumerate(self._tables("task_template", raw), start=1):
            where = f"task_template item {index}"
            name = self._text(where, table, "name")
            start = self._fraction(where, table, "start")
            end = self._fraction(where, table, "end")
            if not Fraction(0) <= start <= end <= Fraction(1):
                raise self.fail(where, "needs 0 <= start <= end <= 1")
            milestone = table.get("milestone", False)
            if not isinstance(milestone, bool):
                raise self.fail(where, "milestone must be true or false")
            tasks.append(TemplateTask(name, start, end, milestone))
        return tuple(tasks)

    def _fraction(self, where: str, table: Mapping[str, Any], name: str) -> Fraction:
        value = table.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self.fail(where, f"{name} must be a number")
        return Fraction(repr(value))

    def _hidden(self, raw: object) -> tuple[ProjectStatus, ...]:
        if not isinstance(raw, list):
            raise self.fail("hidden_statuses", "must be a list")
        statuses: list[ProjectStatus] = []
        for item in raw:  # pyright: ignore[reportUnknownVariableType]
            try:
                status = ProjectStatus(item)
            except ValueError:
                raise self.fail("hidden_statuses", f"unknown status {item!r}") from None
            if status in statuses:
                raise self.fail("hidden_statuses", f"{item!r} is listed twice")
            statuses.append(status)
        return tuple(statuses)

    def _numbers(self, raw: object) -> Numbers:
        if not isinstance(raw, dict):
            raise self.fail("numbers", "must be a table")
        table: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
        defaults = Numbers()
        if unknown := sorted(set(table) - set(vars(defaults))):
            raise self.fail("numbers", f"unknown number {unknown[0]!r}")

        def whole(name: str, low: int, high: int) -> int:
            value = table.get(name, getattr(defaults, name))
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise self.fail("numbers", f"{name} must be a whole number from {low} to {high}")
            return value

        share_raw = table.get("other_work_share", defaults.other_work_share)
        if isinstance(share_raw, bool) or not isinstance(share_raw, int | float | Fraction):
            raise self.fail("numbers", "other_work_share must be a number")
        share = Fraction(repr(share_raw)) if isinstance(share_raw, float) else Fraction(share_raw)
        if not Fraction(0) <= share <= Fraction(1):
            raise self.fail("numbers", "other_work_share must be from 0 to 1")
        numbers = Numbers(
            hours_per_day=whole("hours_per_day", 1, 24),
            day_cap_minutes=whole("day_cap_minutes", 1, 24 * 60),
            timesheet_step_minutes=whole("timesheet_step_minutes", 1, 24 * 60),
            available_days_per_year=whole("available_days_per_year", 1, 366),
            other_work_share=share,
            first_project_number=whole("first_project_number", 1, 10**9),
        )
        if numbers.day_cap_minutes % numbers.timesheet_step_minutes:
            raise self.fail(
                "numbers", "day_cap_minutes must be a multiple of timesheet_step_minutes"
            )
        return numbers


# ---------------------------------------------------------------- values


def _text(value: object, limit: int, what: str) -> str | None:
    if not isinstance(value, str):
        raise FieldValueError(f"{what} must be text")
    text = value.strip()
    if len(text) > limit:
        raise FieldValueError(f"{what} is longer than {limit} characters")
    return text or None


def _whole_id(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FieldValueError(f"{what} must be a positive whole number")
    return value


def _tags(value: object) -> list[str] | None:
    if not isinstance(value, list):
        raise FieldValueError("tags must be a list of text")
    tags: list[str] = []
    items: list[object] = value  # pyright: ignore[reportUnknownVariableType]
    for item in items:
        text = _text(item, MAX_TAG, "a tag")
        if text and text.casefold() not in {t.casefold() for t in tags}:
            tags.append(text)
    if len(tags) > MAX_TAGS:
        raise FieldValueError(f"at most {MAX_TAGS} tags")
    return tags or None


def _number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FieldValueError("must be a number")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FieldValueError("must be a finite number")
        if value.is_integer():
            return int(value)
    return value


def _date(value: object) -> str:
    if not isinstance(value, str):
        raise FieldValueError("must be a date as YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise FieldValueError("must be a date as YYYY-MM-DD") from None


def validate_value(definition: FieldDef, value: object) -> object:
    """The normalised value to store for a detail field; None clears it. Raises FieldValueError."""
    if value is None:
        return None
    match definition.type:
        case FieldType.TEXT:
            return _text(value, MAX_TEXT, definition.label)
        case FieldType.LONG_TEXT:
            return _text(value, MAX_LONG_TEXT, definition.label)
        case FieldType.NUMBER:
            return _number(value)
        case FieldType.DATE:
            return _date(value)
        case FieldType.CHOICE:
            if value not in definition.choices:
                raise FieldValueError(f"must be one of: {', '.join(definition.choices)}")
            return value
        case FieldType.TAGS:
            return _tags(value)
        case FieldType.PERSON:
            return _whole_id(value, "a person")
        case FieldType.PROJECT:
            return _whole_id(value, "a project number")
        case FieldType.YES_NO:
            if not isinstance(value, bool):
                raise FieldValueError("must be yes or no")
            return value
        case _:
            raise FieldValueError(f"{definition.key} is not a detail field")


def known_choices(definition: FieldDef, stored: object) -> bool:
    """False for a stored choice the profile no longer lists (shown as stored, marked unknown)."""
    return definition.type is not FieldType.CHOICE or stored is None or stored in definition.choices


def card_field_keys(cards: Sequence[Card]) -> list[str]:
    """Every field key of the cards in display order."""
    return [f.key for card in cards for f in card.fields]
