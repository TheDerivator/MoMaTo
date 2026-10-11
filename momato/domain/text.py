"""Plain-text helpers for remarks: the excerpts shown in feeds (AP-6)."""

import re

_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_LEADING = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)+")
_EMPHASIS = re.compile(r"(\*\*|__|~~|[*_`])")


def plain_line(line: str) -> str:
    """One Markdown line as the words a reader sees."""
    line = _IMAGE.sub(r"\1", line)
    line = _LINK.sub(r"\1", line)
    line = _LEADING.sub("", line)
    line = _EMPHASIS.sub("", line)
    return " ".join(line.split())


def plain_excerpt(markdown: str, max_lines: int = 3) -> str:
    """The first `max_lines` non-empty lines of a Markdown text, as plain text."""
    lines = (plain_line(line) for line in markdown.splitlines())
    return "\n".join([line for line in lines if line][:max_lines])
