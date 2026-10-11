"""Administration endpoints: org tree, people, sign-in, roles, default grants and the audit log.

Rights are checked by the services: `org.manage` for the org tree and a person's data,
`users.manage` for sign-in, roles, assignments, default grants and the audit log (ADM-1 – ADM-6).
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from momato.api.deps import AccessAdmin, OrgAdmin, PeopleAdmin, Providers
from momato.schemas.admin import (
    AssignmentIn,
    AuditEntryOut,
    AvailabilityIn,
    DefaultGrantIn,
    DefaultGrantOut,
    GroupMappingIn,
    GroupMappingOut,
    OrgNodeCreate,
    OrgNodeUpdate,
    PasswordReset,
    PasswordResetOut,
    PermissionInfo,
    PersonAdminOut,
    PersonCreate,
    PersonUpdate,
    ProviderInfo,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    SignInUpdate,
    StatusIn,
)
from momato.schemas.reference import OrgNodeOut

router = APIRouter(prefix="/admin", tags=["administration"])

Year = Annotated[int, Path(ge=2000, le=2100)]

# ---------------------------------------------------------------- org tree (org.manage)


@router.get("/org")
def org_tree(org: OrgAdmin) -> list[OrgNodeOut]:
    return org.nodes()


@router.post("/org", status_code=status.HTTP_201_CREATED)
def add_node(body: OrgNodeCreate, org: OrgAdmin) -> list[OrgNodeOut]:
    """Add a branch under a node; the whole tree comes back."""
    org.create(body)
    return org.nodes()


@router.patch("/org/{node_id}")
def update_node(node_id: int, body: OrgNodeUpdate, org: OrgAdmin) -> list[OrgNodeOut]:
    """Rename, flag as a department, move (`parent_id`) or reorder (`position`)."""
    org.update(node_id, body)
    return org.nodes()


@router.delete("/org/{node_id}")
def delete_node(node_id: int, org: OrgAdmin) -> list[OrgNodeOut]:
    """Only while nothing refers to the node."""
    org.delete(node_id)
    return org.nodes()


# ---------------------------------------------------------------- people (both rights)


@router.get("/people")
def list_people(people: PeopleAdmin, q: str | None = None) -> list[PersonAdminOut]:
    """Everyone, deactivated people included. Sign-in and rights only for `users.manage`."""
    return people.people(q=q)


@router.post("/people", status_code=status.HTTP_201_CREATED)
def create_person(body: PersonCreate, people: PeopleAdmin) -> PersonAdminOut:
    return people.create(body)


@router.get("/people/{person_id}")
def get_person(person_id: int, people: PeopleAdmin) -> PersonAdminOut:
    return people.get(person_id)


@router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonUpdate, people: PeopleAdmin) -> PersonAdminOut:
    return people.update(person_id, body)


@router.put("/people/{person_id}/availability/{year}")
def set_availability(
    person_id: int, year: Year, body: AvailabilityIn, people: PeopleAdmin
) -> PersonAdminOut:
    return people.set_availability(person_id, year, body.days)


@router.delete("/people/{person_id}/availability/{year}")
def clear_availability(person_id: int, year: Year, people: PeopleAdmin) -> PersonAdminOut:
    return people.clear_availability(person_id, year)


@router.post("/people/{person_id}/deactivate")
def deactivate(person_id: int, people: PeopleAdmin) -> PersonAdminOut:
    """Leaves pickers and planning; history stays; sign-in ends at once."""
    return people.deactivate(person_id)


@router.post("/people/{person_id}/reactivate")
def reactivate(person_id: int, people: PeopleAdmin) -> PersonAdminOut:
    return people.reactivate(person_id)


@router.patch("/people/{person_id}/sign-in")
def update_sign_in(person_id: int, body: SignInUpdate, people: PeopleAdmin) -> PersonAdminOut:
    return people.update_sign_in(person_id, body)


@router.post("/people/{person_id}/password")
def reset_password(person_id: int, body: PasswordReset, people: PeopleAdmin) -> PasswordResetOut:
    """Choose a password or let the server generate one (shown once); changed at first sign-in."""
    return people.reset_password(person_id, body)


@router.put("/people/{person_id}/status")
def set_status(person_id: int, body: StatusIn, people: PeopleAdmin) -> PersonAdminOut:
    """Suspend or reactivate the sign-in (users.manage); suspending ends their sessions."""
    return people.set_status(person_id, body.status)


@router.post("/people/{person_id}/assignments", status_code=status.HTTP_201_CREATED)
def add_assignment(person_id: int, body: AssignmentIn, people: PeopleAdmin) -> PersonAdminOut:
    return people.assign(person_id, body)


@router.delete("/people/{person_id}/assignments/{assignment_id}")
def remove_assignment(person_id: int, assignment_id: int, people: PeopleAdmin) -> PersonAdminOut:
    return people.unassign(person_id, assignment_id)


# ---------------------------------------------------------------- roles and grants (users.manage)


@router.get("/permissions")
def permissions(access: AccessAdmin) -> list[PermissionInfo]:
    return access.permissions()


@router.get("/roles")
def list_roles(access: AccessAdmin) -> list[RoleOut]:
    return access.roles()


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, access: AccessAdmin) -> RoleOut:
    return access.create_role(body)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleUpdate, access: AccessAdmin) -> RoleOut:
    return access.update_role(role_id, body)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, access: AccessAdmin) -> None:
    access.delete_role(role_id)


@router.get("/default-grants")
def list_default_grants(access: AccessAdmin) -> list[DefaultGrantOut]:
    return access.default_grants()


@router.post("/default-grants", status_code=status.HTTP_201_CREATED)
def add_default_grant(body: DefaultGrantIn, access: AccessAdmin) -> list[DefaultGrantOut]:
    access.add_default_grant(body.audience, body.role_key, body.scope)
    return access.default_grants()


@router.delete("/default-grants/{grant_id}")
def remove_default_grant(grant_id: int, access: AccessAdmin) -> list[DefaultGrantOut]:
    access.remove_default_grant(grant_id)
    return access.default_grants()


# ---------------------------------------------------------------- single sign-on (users.manage)


@router.get("/sso-providers")
def sso_providers(access: AccessAdmin, providers: Providers) -> list[ProviderInfo]:
    """The configured SSO providers (none when only built-in sign-in is used)."""
    del access  # only for the permission check
    return [
        *(
            ProviderInfo(name=p.name, display_name=p.display_name, kind="redirect")
            for p in providers.redirect.values()
        ),
        *(
            ProviderInfo(name=p.name, display_name=p.display_name, kind="ambient")
            for p in providers.ambient
        ),
        *(
            [
                ProviderInfo(
                    name=providers.negotiate.name,
                    display_name=providers.negotiate.display_name,
                    kind="negotiate",
                )
            ]
            if providers.negotiate
            else []
        ),
    ]


@router.get("/group-mappings")
def list_group_mappings(access: AccessAdmin) -> list[GroupMappingOut]:
    """Identity-provider groups whose members hold a role while they are in the group."""
    return access.group_mappings()


@router.post("/group-mappings", status_code=status.HTTP_201_CREATED)
def add_group_mapping(body: GroupMappingIn, access: AccessAdmin) -> list[GroupMappingOut]:
    access.add_group_mapping(body.provider, body.group_name, body.role_key, body.scope)
    return access.group_mappings()


@router.delete("/group-mappings/{mapping_id}")
def remove_group_mapping(mapping_id: int, access: AccessAdmin) -> list[GroupMappingOut]:
    access.remove_group_mapping(mapping_id)
    return access.group_mappings()


# ---------------------------------------------------------------- audit log (users.manage)


@router.get("/audit")
def audit_log(
    access: AccessAdmin,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: int | None = None,
    action: str | None = None,
    actor_id: int | None = None,
) -> list[AuditEntryOut]:
    """Newest first; page back with `before_id`; `action` matches a prefix such as `user.`."""
    return access.audit_log(limit=limit, before_id=before_id, action=action, actor_id=actor_id)
