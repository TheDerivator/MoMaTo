"""Plain-text excerpts of Markdown remarks, for feeds. [AP-6]"""

import pytest

from momato.domain.text import plain_excerpt, plain_line


@pytest.mark.parametrize(
    ("markdown", "plain"),
    [
        ("Just words", "Just words"),
        ("- a list item", "a list item"),
        ("* another  item", "another item"),
        ("1. numbered", "numbered"),
        ("## A heading", "A heading"),
        ("> quoted text", "quoted text"),
        ("**bold** and _italic_ and `code`", "bold and italic and code"),
        ("~~struck~~", "struck"),
        ("a [link](https://example.org/x) here", "a link here"),
        ("![the picture](/api/attachments/3) after", "the picture after"),
        ("![](/api/attachments/3)", ""),
        ("   spaced     out   ", "spaced out"),
    ],
)
def test_a_line_loses_its_markup(markdown: str, plain: str) -> None:
    assert plain_line(markdown) == plain


def test_an_excerpt_is_the_first_non_empty_lines() -> None:
    text = "Done:\n- First week of data\n\n- Dashboard shared\n\nNext steps:\n- Tune alerts"
    assert plain_excerpt(text) == "Done:\nFirst week of data\nDashboard shared"
    assert plain_excerpt(text, max_lines=1) == "Done:"
    assert plain_excerpt("") == ""
    assert plain_excerpt("\n\n   \n") == ""
