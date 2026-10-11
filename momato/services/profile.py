"""Load the deployment profile named by `MOMATO_PROFILE` from momato/profiles/ (D-009, §7)."""

import re
import tomllib
from pathlib import Path

from momato.domain.fields import Profile, ProfileError

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
_NAME = re.compile(r"[a-z][a-z0-9_-]*")


def available_profiles(directory: Path | None = None) -> list[str]:
    folder = directory or PROFILES_DIR
    return sorted(p.stem for p in folder.glob("*.toml"))


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Read and validate a profile. A broken one raises `ProfileError` naming the problem, so the
    server refuses to start rather than run with fields it cannot make sense of."""
    folder = directory or PROFILES_DIR
    if not _NAME.fullmatch(name):
        raise ProfileError(f"profile {name!r}: use a name of lowercase letters, digits, - and _")
    path = folder / f"{name}.toml"
    if not path.is_file():
        known = ", ".join(available_profiles(folder)) or "none"
        raise ProfileError(f"profile {name!r} does not exist (available: {known})")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ProfileError(f"profile {name!r}: not valid TOML: {error}") from error
    return Profile.from_mapping(name, data)
