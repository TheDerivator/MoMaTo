"""The profile model, its validation errors and the validation of detail values. [DT-2]"""

import copy
from fractions import Fraction
from typing import Any

import pytest

from momato.domain import fields as f
from momato.domain.projects import ProjectStatus


def valid() -> dict[str, Any]:
    """A minimal valid profile as parsed from TOML (a fresh copy per call)."""
    return copy.deepcopy(
        {
            "hidden_statuses": ["stopped"],
            "numbers": {"hours_per_day": 8},
            "cards": [
                {
                    "key": "identification",
                    "title": "Identification",
                    "fields": [
                        {"key": "number", "label": "Project number", "core": "number"},
                        {"key": "erp_order", "label": "ERP order", "type": "text"},
                        {
                            "key": "activity",
                            "label": "Activity type",
                            "type": "choice",
                            "choices": ["Project", "Study"],
                        },
                    ],
                }
            ],
            "categories": [
                {"key": "meetings", "label": "Meetings", "kind": "other_work"},
                {"key": "vacation", "label": "Vacation", "kind": "time_off"},
            ],
            "task_template": [
                {"name": "Study", "start": 0.0, "end": 0.5},
                {"name": "Build", "start": 0.5, "end": 1.0, "milestone": True},
            ],
        }
    )


def load(data: dict[str, Any]) -> f.Profile:
    return f.Profile.from_mapping("test", data)


def test_a_valid_profile_is_built() -> None:
    profile = load(valid())
    assert profile.name == "test"
    assert [c.key for c in profile.cards] == ["identification"]
    assert [x.key for x in profile.cards[0].fields] == ["number", "erp_order", "activity"]
    assert profile.cards[0].fields[0].core == "number"
    assert set(profile.detail_fields) == {"erp_order", "activity"}
    assert profile.detail_fields["activity"].choices == ("Project", "Study")
    assert [c.kind for c in profile.categories] == [
        f.CategoryKind.OTHER_WORK,
        f.CategoryKind.TIME_OFF,
    ]
    assert [c.key for c in profile.categories_of(f.CategoryKind.TIME_OFF)] == ["vacation"]
    assert [t.milestone for t in profile.task_template] == [False, True]
    assert profile.task_template[0].end == Fraction(1, 2)
    assert profile.hidden_statuses == (ProjectStatus.STOPPED,)
    assert profile.numbers.hours_per_day == 8
    assert profile.numbers.other_work_share == Fraction(1, 10)
    assert f.card_field_keys(profile.cards) == ["number", "erp_order", "activity"]


def test_defaults_apply_to_a_profile_with_only_categories() -> None:
    data = {"categories": valid()["categories"]}
    profile = load(data)
    assert profile.cards == ()
    assert profile.task_template == ()
    assert profile.hidden_statuses == (ProjectStatus.STOPPED,)
    assert profile.numbers == f.Numbers()


def test_numbers_can_be_set() -> None:
    data = valid()
    data["numbers"] = {
        "hours_per_day": 7,
        "day_cap_minutes": 480,
        "timesheet_step_minutes": 30,
        "available_days_per_year": 210,
        "other_work_share": 0.15,
        "first_project_number": 5000,
    }
    numbers = load(data).numbers
    assert (numbers.hours_per_day, numbers.day_cap_minutes, numbers.timesheet_step_minutes) == (
        7,
        480,
        30,
    )
    assert (numbers.available_days_per_year, numbers.first_project_number) == (210, 5000)
    assert numbers.other_work_share == Fraction(3, 20)


def test_hidden_statuses_can_be_empty_or_several() -> None:
    data = valid()
    data["hidden_statuses"] = []
    assert load(data).hidden_statuses == ()
    data["hidden_statuses"] = ["stopped", "rejected"]
    assert load(data).hidden_statuses == (ProjectStatus.STOPPED, ProjectStatus.REJECTED)


def broken(mutate: Any) -> dict[str, Any]:
    data = valid()
    mutate(data)
    return data


BROKEN: list[tuple[str, Any, str]] = [
    ("unknown setting", lambda d: d.update(colour="red"), "unknown setting 'colour'"),
    (
        "unknown field type",
        lambda d: d["cards"][0]["fields"][1].update(type="money"),
        "unknown type 'money'",
    ),
    (
        "duplicate field key",
        lambda d: d["cards"][0]["fields"].append(
            {"key": "erp_order", "label": "x", "type": "text"}
        ),
        "duplicate field key",
    ),
    (
        "duplicate card key",
        lambda d: d["cards"].append({"key": "identification", "title": "Again", "fields": []}),
        "duplicate card key",
    ),
    (
        "choice without choices",
        lambda d: d["cards"][0]["fields"][2].pop("choices"),
        "needs a non-empty list of choices",
    ),
    (
        "choice with empty choices",
        lambda d: d["cards"][0]["fields"][2].update(choices=[]),
        "needs a non-empty list of choices",
    ),
    (
        "choice with blank entry",
        lambda d: d["cards"][0]["fields"][2].update(choices=["a", " "]),
        "choices must be non-empty text",
    ),
    (
        "duplicate choices",
        lambda d: d["cards"][0]["fields"][2].update(choices=["a", "a"]),
        "duplicate choices",
    ),
    (
        "choices on a text field",
        lambda d: d["cards"][0]["fields"][1].update(choices=["a"]),
        "only a choice field has choices",
    ),
    ("category without kind", lambda d: d["categories"][0].pop("kind"), "kind is required"),
    (
        "category with unknown kind",
        lambda d: d["categories"][0].update(kind="holiday"),
        "kind is required",
    ),
    (
        "duplicate category",
        lambda d: d["categories"].append({"key": "meetings", "label": "M", "kind": "other_work"}),
        "duplicate category key",
    ),
    ("no time off category", lambda d: d["categories"].pop(1), "at least one of kind 'time_off'"),
    (
        "no other work category",
        lambda d: d["categories"].pop(0),
        "at least one of kind 'other_work'",
    ),
    (
        "field with core and type",
        lambda d: d["cards"][0]["fields"][0].update(type="text"),
        "exactly one of core and type",
    ),
    (
        "field with neither",
        lambda d: d["cards"][0]["fields"][1].pop("type"),
        "exactly one of core and type",
    ),
    (
        "unknown core field",
        lambda d: d["cards"][0]["fields"][0].update(core="budget"),
        "unknown core field 'budget'",
    ),
    (
        "core field twice",
        lambda d: d["cards"][0]["fields"].append({"key": "again", "label": "x", "core": "number"}),
        "shown twice",
    ),
    (
        "detail named like a core field",
        lambda d: d["cards"][0]["fields"][1].update(key="priority"),
        "named like a core field",
    ),
    ("bad key", lambda d: d["cards"][0]["fields"][1].update(key="ERP Order"), "must be lowercase"),
    ("missing label", lambda d: d["cards"][0]["fields"][1].pop("label"), "label is required"),
    ("missing card title", lambda d: d["cards"][0].pop("title"), "title is required"),
    (
        "template start after end",
        lambda d: d["task_template"][0].update(start=0.9, end=0.1),
        "0 <= start <= end <= 1",
    ),
    (
        "template out of range",
        lambda d: d["task_template"][0].update(end=1.5),
        "0 <= start <= end <= 1",
    ),
    (
        "template text number",
        lambda d: d["task_template"][0].update(start="soon"),
        "start must be a number",
    ),
    (
        "template milestone not boolean",
        lambda d: d["task_template"][0].update(milestone="yes"),
        "milestone must be true or false",
    ),
    ("template without name", lambda d: d["task_template"][0].pop("name"), "name is required"),
    (
        "unknown hidden status",
        lambda d: d.update(hidden_statuses=["gone"]),
        "unknown status 'gone'",
    ),
    (
        "hidden status twice",
        lambda d: d.update(hidden_statuses=["stopped", "stopped"]),
        "listed twice",
    ),
    ("hidden statuses not a list", lambda d: d.update(hidden_statuses="stopped"), "must be a list"),
    ("unknown number", lambda d: d["numbers"].update(weeks=3), "unknown number 'weeks'"),
    (
        "number out of range",
        lambda d: d["numbers"].update(hours_per_day=30),
        "hours_per_day must be a whole number from 1 to 24",
    ),
    (
        "number not whole",
        lambda d: d["numbers"].update(available_days_per_year=220.5),
        "available_days_per_year must be a whole number",
    ),
    (
        "number is a boolean",
        lambda d: d["numbers"].update(hours_per_day=True),
        "hours_per_day must be a whole number",
    ),
    (
        "share out of range",
        lambda d: d["numbers"].update(other_work_share=1.5),
        "other_work_share must be from 0 to 1",
    ),
    (
        "share not a number",
        lambda d: d["numbers"].update(other_work_share="a tenth"),
        "other_work_share must be a number",
    ),
    (
        "cap not a multiple of the step",
        lambda d: d["numbers"].update(day_cap_minutes=100, timesheet_step_minutes=60),
        "multiple of timesheet_step_minutes",
    ),
    ("numbers not a table", lambda d: d.update(numbers=[1]), "must be a table"),
    ("cards not a list of tables", lambda d: d.update(cards="none"), "must be a list of tables"),
]


@pytest.mark.parametrize(("name", "mutate", "message"), BROKEN, ids=[b[0] for b in BROKEN])
def test_a_broken_profile_is_refused_with_a_message_naming_the_problem(
    name: str, mutate: Any, message: str
) -> None:
    del name
    with pytest.raises(f.ProfileError, match=message) as error:
        load(broken(mutate))
    assert "profile 'test'" in str(error.value)


def test_error_messages_name_the_card_and_field() -> None:
    data = broken(lambda d: d["cards"][0]["fields"][1].update(type="money"))
    with pytest.raises(f.ProfileError) as error:
        load(data)
    assert "card 'identification': field 'erp_order'" in str(error.value)


# ---------------------------------------------------------------- values


def definition(kind: f.FieldType, **extra: Any) -> f.FieldDef:
    return f.FieldDef("x", "Label", kind, **extra)


VALID_VALUES: list[tuple[f.FieldType, Any, Any]] = [
    (f.FieldType.TEXT, "  hello  ", "hello"),
    (f.FieldType.TEXT, "   ", None),
    (f.FieldType.TEXT, None, None),
    (f.FieldType.LONG_TEXT, "a\nb", "a\nb"),
    (f.FieldType.NUMBER, 12, 12),
    (f.FieldType.NUMBER, 12.0, 12),
    (f.FieldType.NUMBER, 12.5, 12.5),
    (f.FieldType.NUMBER, -3, -3),
    (f.FieldType.DATE, "2026-10-08", "2026-10-08"),
    (f.FieldType.TAGS, [" sensors ", "data", "Sensors", ""], ["sensors", "data"]),
    (f.FieldType.TAGS, [], None),
    (f.FieldType.PERSON, 7, 7),
    (f.FieldType.PROJECT, 4102, 4102),
    (f.FieldType.YES_NO, True, True),
    (f.FieldType.YES_NO, False, False),
]


@pytest.mark.parametrize(("kind", "value", "expected"), VALID_VALUES)
def test_valid_values_are_normalised(kind: f.FieldType, value: Any, expected: Any) -> None:
    assert f.validate_value(definition(kind), value) == expected


def test_a_choice_must_be_listed() -> None:
    choice = definition(f.FieldType.CHOICE, choices=("Easy", "Hard"))
    assert f.validate_value(choice, "Easy") == "Easy"
    with pytest.raises(f.FieldValueError, match="one of: Easy, Hard"):
        f.validate_value(choice, "Moderate")


INVALID_VALUES: list[tuple[f.FieldType, Any, str]] = [
    (f.FieldType.TEXT, 5, "must be text"),
    (f.FieldType.TEXT, "x" * 301, "longer than 300"),
    (f.FieldType.LONG_TEXT, "x" * 10_001, "longer than 10000"),
    (f.FieldType.NUMBER, "12", "must be a number"),
    (f.FieldType.NUMBER, True, "must be a number"),
    (f.FieldType.NUMBER, float("nan"), "finite"),
    (f.FieldType.NUMBER, float("inf"), "finite"),
    (f.FieldType.DATE, "08/10/2026", "YYYY-MM-DD"),
    (f.FieldType.DATE, "2026-02-30", "YYYY-MM-DD"),
    (f.FieldType.DATE, 20261008, "YYYY-MM-DD"),
    (f.FieldType.TAGS, "a,b", "list of text"),
    (f.FieldType.TAGS, [f"t{i}" for i in range(21)], "at most 20 tags"),
    (f.FieldType.TAGS, ["x" * 51], "longer than 50"),
    (f.FieldType.TAGS, [1], "must be text"),
    (f.FieldType.PERSON, 0, "positive whole number"),
    (f.FieldType.PERSON, "3", "positive whole number"),
    (f.FieldType.PERSON, True, "positive whole number"),
    (f.FieldType.PROJECT, -4, "positive whole number"),
    (f.FieldType.YES_NO, "yes", "yes or no"),
    (f.FieldType.YES_NO, 1, "yes or no"),
]


@pytest.mark.parametrize(("kind", "value", "message"), INVALID_VALUES)
def test_invalid_values_are_refused(kind: f.FieldType, value: Any, message: str) -> None:
    with pytest.raises(f.FieldValueError, match=message):
        f.validate_value(definition(kind), value)


def test_a_core_row_is_not_a_detail_field() -> None:
    core = f.FieldDef("number", "Project number", core="number")
    assert f.validate_value(core, None) is None
    with pytest.raises(f.FieldValueError, match="not a detail field"):
        f.validate_value(core, 1)


def test_an_unlisted_stored_choice_is_known_as_unknown() -> None:
    choice = definition(f.FieldType.CHOICE, choices=("Easy", "Hard"))
    assert f.known_choices(choice, "Easy")
    assert f.known_choices(choice, None)
    assert not f.known_choices(choice, "Moderate")
    assert f.known_choices(definition(f.FieldType.TEXT), "anything")
