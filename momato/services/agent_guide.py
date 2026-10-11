"""The guide for AI agents (TOK-4): Markdown that tells an agent how to use MoMaTo's API with a
token. The hand-written part is `data/agent-guide.md`; the endpoint list is generated from the
OpenAPI document, so it always matches the API it describes."""

from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent / "data" / "agent-guide.md"

# Endpoints an agent has no use for: signing in (a token is mandatory), managing tokens (people
# do that in MoMaTo itself), and administration (never through a token).
HIDDEN_TAGS = frozenset({"auth", "tokens", "administration"})
KEPT = frozenset({("get", "/api/auth/me")})
METHODS = ("get", "post", "put", "patch", "delete")

type Schema = dict[str, Any]


def _component(spec: Schema, ref: str) -> tuple[str, Schema]:
    name = ref.rsplit("/", 1)[-1]
    return name, spec.get("components", {}).get("schemas", {}).get(name, {})


def type_text(spec: Schema, schema: Schema) -> str:
    """A short type: `string`, `integer[]`, `date`, `idea|started|done`, `ProjectStatus`, with
    `|null` when null is allowed."""
    if "$ref" in schema:
        name, target = _component(spec, schema["$ref"])
        return "|".join(str(v) for v in target["enum"]) if "enum" in target else name
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        text = " or ".join(type_text(spec, o) for o in options) or "null"
        return text + ("|null" if len(options) < len(schema["anyOf"]) else "")
    if "enum" in schema:
        return "|".join(str(v) for v in schema["enum"])
    kind = schema.get("type", "any")
    if kind == "array":
        return f"({type_text(spec, schema.get('items', {}))})[]"
    return schema.get("format", kind) if kind == "string" else kind


def _fields(spec: Schema, schema: Schema) -> str:
    if "$ref" in schema:
        schema = _component(spec, schema["$ref"])[1]
    required = set(schema.get("required", []))
    return ", ".join(
        f"`{name}`{'*' if name in required else ''} {type_text(spec, prop)}"
        for name, prop in schema.get("properties", {}).items()
    )


def _summary(operation: Schema) -> str:
    text = (operation.get("description") or "").split("\n\n")[0]
    return " ".join(text.split()) or operation.get("summary", "")


def endpoint_list(spec: Schema) -> str:
    """Every endpoint an agent may use, grouped by the API's tags, with what it takes."""
    groups: dict[str, list[str]] = {}
    for path, operations in spec.get("paths", {}).items():
        for method in METHODS:
            operation = operations.get(method)
            if operation is None:
                continue
            tag = (operation.get("tags") or ["other"])[0]
            if tag in HIDDEN_TAGS and (method, path) not in KEPT:
                continue
            lines = [f"- `{method.upper()} {path}`: {_summary(operation)}".rstrip(": ")]
            parameters = [p for p in operation.get("parameters", []) if p.get("in") == "query"]
            if parameters:
                query = ", ".join(
                    f"`{p['name']}`{'*' if p.get('required') else ''} "
                    + type_text(spec, p.get("schema", {}))
                    for p in parameters
                )
                lines.append(f"  - query: {query}")
            body = operation.get("requestBody", {}).get("content", {})
            if "application/json" in body:
                lines.append(f"  - body: {_fields(spec, body['application/json']['schema'])}")
            elif "multipart/form-data" in body:
                lines.append("  - body: a file upload (multipart/form-data, field `file`)")
            groups.setdefault(tag, []).extend(lines)
    return "\n\n".join(
        f"### {tag.capitalize()}\n\n" + "\n".join(lines) for tag, lines in groups.items()
    )


def agent_guide(spec: Schema, *, base_url: str) -> str:
    """The whole guide for the board at `base_url` (ending in "/")."""
    return (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("{{base_url}}", base_url)
        .replace("{{api_url}}", base_url + "api/")
        .replace("{{endpoints}}", endpoint_list(spec))
    )
