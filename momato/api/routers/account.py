"""The profile page's data: the signed-in person's own record (ADM-8)."""

from fastapi import APIRouter

from momato.api.deps import Account
from momato.schemas.account import AccountOut

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
def my_account(account: Account) -> AccountOut:
    """Name, job title, place in the organisation, work pattern and availability."""
    return account.account()
