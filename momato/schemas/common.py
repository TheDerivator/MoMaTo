"""Field types shared by the request schemas: names are trimmed before their length is checked."""

from typing import Annotated

from pydantic import StringConstraints

# "   " is an empty name (422), not a blank one that slips through and is stored as "".
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Name200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
