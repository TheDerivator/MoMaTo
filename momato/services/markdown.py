"""Markdown → safe HTML for remarks (RM-3).

CommonMark plus tables and strikethrough; single newlines become line breaks (chat style).
Extras: `@name` mentions are highlighted (no notifications), `#4102` links to that project.
Raw HTML in the source is not interpreted, and the output is sanitized with nh3 (an allow-list):
images may only come from this app's own attachments, links only use http(s)/mailto or are
relative, and every link gets rel="noopener noreferrer".
"""

import re
from html import escape

import nh3
from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.token import Token

ATTACHMENT_URL_PREFIX = "api/attachments/"

_DECORATIONS = re.compile(
    r"(?P<mention>(?<![\w@])@\w[\w.\-]*\w|(?<![\w@])@\w)"
    r"|(?P<project>(?<![\w&#/])#(?P<number>\d{3,7})(?![\w-]))"
)

_TAGS = {
    "p", "br", "strong", "em", "s", "del", "code", "pre", "blockquote", "ul", "ol", "li",
    "a", "img", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
    "table", "thead", "tbody", "tr", "th", "td", "span",
}  # fmt: skip
_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "ol": {"start"},
    "th": {"style"},
    "td": {"style"},
}
_CLASSES = {"a": {"project-ref"}, "span": {"mention"}}  # nh3: classes only via this allow-list


def _text(content: str) -> Token:
    token = Token("text", "", 0)
    token.content = content
    return token


def _html(content: str) -> Token:
    token = Token("html_inline", "", 0)
    token.content = content
    return token


def _decorate(state: StateCore) -> None:
    """Turn @mentions and #numbers in plain text (not inside links or code) into markup."""
    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        result: list[Token] = []
        in_link = 0
        for token in block.children:
            if token.type == "link_open":
                in_link += 1
            elif token.type == "link_close":
                in_link -= 1
            if token.type != "text" or in_link or not _DECORATIONS.search(token.content):
                result.append(token)
                continue
            position = 0
            for match in _DECORATIONS.finditer(token.content):
                if match.start() > position:
                    result.append(_text(token.content[position : match.start()]))
                word = escape(match.group())
                if match.group("mention"):
                    result.append(_html(f'<span class="mention">{word}</span>'))
                else:
                    number = match.group("number")
                    result.append(
                        _html(f'<a class="project-ref" href="projects/{number}">{word}</a>')
                    )
                position = match.end()
            if position < len(token.content):
                result.append(_text(token.content[position:]))
        block.children = result


def _build() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "breaks": True})
    md.enable(["table", "strikethrough"])
    md.core.ruler.push("momato_decorate", _decorate)
    return md


_MD = _build()


def _filter_attribute(tag: str, attribute: str, value: str) -> str | None:
    if tag == "img" and attribute == "src":
        return value if value.startswith(ATTACHMENT_URL_PREFIX) else None
    if attribute == "style":  # table alignment only
        return value if re.fullmatch(r"text-align:\s*(left|right|center)", value) else None
    return value


def render_markdown(source: str) -> str:
    """Safe HTML for a remark's or reply's body."""
    return nh3.clean(
        _MD.render(source),
        tags=_TAGS,
        attributes=_ATTRIBUTES,
        allowed_classes=_CLASSES,
        attribute_filter=_filter_attribute,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )


def attachment_ids_in(source: str) -> set[str]:
    """Public ids of this app's attachments that a Markdown body refers to."""
    return set(re.findall(rf"{re.escape(ATTACHMENT_URL_PREFIX)}([0-9a-f]{{32}})", source))
