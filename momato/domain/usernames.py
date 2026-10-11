"""Login names: derived from a person's name, ASCII, lowercase, unique."""

import re
import unicodedata

_SPECIAL = {"ß": "ss", "ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "ð": "d", "þ": "th"}
MAX_LENGTH = 90


def base_username(name: str) -> str:
    """`Chloé Martens` becomes `chloe.martens`; names without letters become `user`."""
    folded = "".join(_SPECIAL.get(c, c) for c in name.casefold())
    ascii_only = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    words = re.sub(r"[^a-z0-9]+", ".", ascii_only).strip(".")
    return words[:MAX_LENGTH].strip(".") or "user"


def unique_username(name: str, taken: set[str]) -> str:
    """`base_username(name)`, with -2, -3, ... added until it is not in `taken`."""
    base = base_username(name)
    candidate, number = base, 1
    while candidate in taken:
        number += 1
        candidate = f"{base}-{number}"
    return candidate
