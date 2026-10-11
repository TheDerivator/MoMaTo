"""Project numbers (R4.7, D-017): the highest existing number plus one, or the profile's first."""


def next_project_number(highest_existing: int | None, first_number: int) -> int:
    """Numbers are unique, never change, and are the project's permalink."""
    if highest_existing is None:
        return first_number
    return highest_existing + 1
