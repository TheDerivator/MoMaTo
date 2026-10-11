"""API token endpoints (TOK-1 – TOK-4): your own tokens, anyone's for people who manage users, and
the guide for AI agents (Markdown, generated with the API's own endpoint list)."""

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse

from momato.api.deps import AppSettings, Tokens
from momato.schemas.tokens import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from momato.services.agent_guide import agent_guide

router = APIRouter(tags=["tokens"])


@router.get("/auth/tokens")
def my_tokens(tokens: Tokens) -> list[ApiTokenOut]:
    """Your API tokens that are not revoked (expired ones included), newest first."""
    return tokens.mine()


@router.post("/auth/tokens", status_code=status.HTTP_201_CREATED)
def create_token(body: ApiTokenCreate, tokens: Tokens) -> ApiTokenCreated:
    """A new token acting as you; `secret` is shown this once. Not possible through a token."""
    return tokens.create(body)


@router.delete("/auth/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: int, tokens: Tokens) -> None:
    tokens.revoke(token_id)


@router.get("/admin/people/{person_id}/tokens", tags=["administration"])
def person_tokens(person_id: int, tokens: Tokens) -> list[ApiTokenOut]:
    """A person's tokens that are not revoked (`users.manage`)."""
    return tokens.of_user(person_id)


@router.delete(
    "/admin/people/{person_id}/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["administration"],
)
def revoke_person_token(person_id: int, token_id: int, tokens: Tokens) -> None:
    tokens.revoke_of_user(person_id, token_id)


@router.get("/agent-guide", response_class=PlainTextResponse, tags=["meta"])
def guide(request: Request, settings: AppSettings) -> PlainTextResponse:
    """How an AI agent uses this API with a token (Markdown), with every endpoint it may use."""
    if settings.public_url:
        base = settings.public_url.rstrip("/") + "/"
    else:
        base = str(request.base_url).rstrip("/") + settings.normalized_base_path
    text = agent_guide(request.app.openapi(), base_url=base)
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")
