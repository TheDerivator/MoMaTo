"""The deployment profile loader and the default profile, which is the design's. [DT-2]"""

from pathlib import Path

import pytest

from momato.cli import main
from momato.config import Settings
from momato.domain.fields import CategoryKind, FieldType, ProfileError
from momato.domain.projects import ProjectStatus
from momato.services.profile import PROFILES_DIR, available_profiles, load_profile
from momato.web import create_app


def test_the_default_profile_is_the_designs_cards_and_fields() -> None:
    profile = load_profile("default")
    assert [c.title for c in profile.cards] == [
        "Identification",
        "Organisation",
        "Classification",
        "Involvement",
    ]
    rows = {c.key: [f.label for f in c.fields] for c in profile.cards}
    assert rows["identification"] == [
        "Project number",
        "ERP order",
        "Original project",
        "Activity type",
    ]
    assert rows["organisation"] == ["Department", "Sponsor", "Budget owner", "Steering committee"]
    assert rows["classification"] == [
        "Priority",
        "Strategic axis",
        "Process",
        "Programme",
        "Tags",
        "Ease of execution",
    ]
    assert rows["involvement"] == [
        "Operations & maintenance",
        "Procurement",
        "Engineering",
        "Planning phase",
    ]
    core = {f.core for c in profile.cards for f in c.fields if f.core}
    assert core == {"number", "department", "priority"}
    assert len(profile.detail_fields) == 15
    kinds = {f.key: f.type for f in profile.detail_fields.values()}
    assert kinds["original_project"] is FieldType.PROJECT
    assert kinds["sponsor"] is FieldType.PERSON
    assert kinds["tags"] is FieldType.TAGS
    assert kinds["engineering"] is FieldType.YES_NO
    assert profile.detail_fields["ease_of_execution"].choices == ("Easy", "Moderate", "Hard")


def test_the_default_profile_has_the_designs_categories_template_and_numbers() -> None:
    profile = load_profile("default")
    assert [c.label for c in profile.categories_of(CategoryKind.OTHER_WORK)] == [
        "Meetings",
        "Training",
        "Admin",
    ]
    assert [c.label for c in profile.categories_of(CategoryKind.TIME_OFF)] == [
        "Vacation",
        "Out of office",
    ]
    assert [t.name for t in profile.task_template] == [
        "Study & scoping",
        "Supplier offers",
        "Order & delivery",
        "Installation",
        "Commissioning",
        "Handover & close-out",
    ]
    assert [t.milestone for t in profile.task_template] == [False, False, True, False, True, False]
    assert profile.hidden_statuses == (ProjectStatus.STOPPED,)
    numbers = profile.numbers
    assert (numbers.hours_per_day, numbers.day_cap_minutes, numbers.timesheet_step_minutes) == (
        8,
        600,
        60,
    )
    assert (numbers.available_days_per_year, numbers.first_project_number) == (220, 1000)
    assert numbers.other_work_share * 40 == 4  # 4 hours of 40


def test_available_profiles_lists_the_toml_files() -> None:
    assert "default" in available_profiles()
    assert (PROFILES_DIR / "default.toml").is_file()


def test_an_unknown_profile_names_the_available_ones() -> None:
    with pytest.raises(ProfileError, match=r"'nope' does not exist \(available: .*default"):
        load_profile("nope")


@pytest.mark.parametrize("name", ["../secrets", "Default", "a b", "", "1x", "x/y"])
def test_a_profile_name_cannot_point_elsewhere(name: str) -> None:
    with pytest.raises(ProfileError, match="lowercase letters"):
        load_profile(name)


def test_invalid_toml_is_reported(tmp_path: Path) -> None:
    (tmp_path / "broken.toml").write_text("cards = [", encoding="utf-8")
    with pytest.raises(ProfileError, match="not valid TOML"):
        load_profile("broken", tmp_path)


def test_a_profile_in_another_folder_is_validated(tmp_path: Path) -> None:
    (tmp_path / "variant.toml").write_text(
        '[[categories]]\nkey = "x"\nlabel = "X"\n', encoding="utf-8"
    )
    with pytest.raises(ProfileError, match="category 'x': kind is required"):
        load_profile("variant", tmp_path)


def test_a_variant_profile_loads(tmp_path: Path) -> None:
    (tmp_path / "variant.toml").write_text(
        "\n".join(
            [
                "[[categories]]",
                'key = "meetings"',
                'label = "Meetings"',
                'kind = "other_work"',
                "[[categories]]",
                'key = "leave"',
                'label = "Leave"',
                'kind = "time_off"',
                "[[cards]]",
                'key = "extra"',
                'title = "Extra"',
                "[[cards.fields]]",
                'key = "cost_centre"',
                'label = "Cost centre"',
                'type = "text"',
            ]
        ),
        encoding="utf-8",
    )
    profile = load_profile("variant", tmp_path)
    assert list(profile.detail_fields) == ["cost_centre"]


def test_a_broken_profile_stops_the_app_from_starting(settings: Settings) -> None:
    with pytest.raises(ProfileError, match="'missing' does not exist"):
        create_app(settings.model_copy(update={"profile": "missing"}))


def test_a_broken_profile_stops_the_server_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr("momato.services.profile.PROFILES_DIR", tmp_path)
    monkeypatch.setenv("MOMATO_PROFILE", "default")
    from momato.config import get_settings

    get_settings.cache_clear()
    try:
        assert main(["serve"]) == 1
    finally:
        get_settings.cache_clear()
    assert "Cannot start: profile 'default' does not exist" in capsys.readouterr().out
