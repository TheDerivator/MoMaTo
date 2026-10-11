"""The access policy against a real database: personas × permissions × nodes. [AUTH-2]

The org tree used here:

    Brightwater (root, no department)
    ├─ STL (department)
    │   ├─ Quality
    │   │   └─ Lab
    │   └─ Process
    ├─ R&D (department)
    │   └─ Coatings
    └─ Staff (not a department)

Expectations are written out by hand per persona, not computed by the code under test.
"""

from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import (
    DefaultGrant,
    OrgNode,
    Project,
    Role,
    RoleAssignment,
    User,
)
from momato.db.models.people import UserKind
from momato.domain.access import (
    Audience,
    Permission,
    Scope,
)
from momato.domain.errors import (
    AuthenticationRequiredError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal, anonymous_principal, principal_for_user
from tests.factories import make_org, make_project, make_user

ALL_NODES = ["root", "stl", "quality", "lab", "process", "rd", "coatings", "staff"]
STL_BRANCH = {"stl", "quality", "lab", "process"}
RD_BRANCH = {"rd", "coatings"}


@dataclass
class World:
    session: Session
    nodes: dict[str, OrgNode]

    def role(self, key: str) -> Role:
        role = self.session.scalar(select(Role).where(Role.key == key))
        assert role is not None
        return role

    def person(self, name: str, node: str | None, *roles: tuple[str, Scope]) -> User:
        user = make_user(self.session, name, self.nodes[node] if node else None)
        for key, scope in roles:
            assignment = RoleAssignment(user_id=user.id, role_id=self.role(key).id)
            assignment.scope = self._resolved(scope)
            self.session.add(assignment)
        self.session.flush()
        return user

    def _resolved(self, scope: Scope) -> Scope:
        return scope

    def node_scope(self, name: str) -> Scope:
        return Scope.node(self.nodes[name].id)

    def principal(self, user: User) -> Principal:
        self.session.flush()
        return principal_for_user(self.session, user)

    def allowed_nodes(self, principal: Principal, permission: Permission) -> set[str]:
        return {n for n, node in self.nodes.items() if principal.can(permission, node.id)}


@pytest.fixture
def world(session: Session) -> World:
    root = make_org(session, "Brightwater")
    stl = make_org(session, "STL", root, department=True)
    quality = make_org(session, "Quality", stl)
    lab = make_org(session, "Lab", quality)
    process = make_org(session, "Process", stl)
    rd = make_org(session, "R&D", root, department=True)
    coatings = make_org(session, "Coatings", rd)
    staff = make_org(session, "Staff", root)
    nodes = {
        "root": root,
        "stl": stl,
        "quality": quality,
        "lab": lab,
        "process": process,
        "rd": rd,
        "coatings": coatings,
        "staff": staff,
    }
    return World(session, nodes)


# ---------------------------------------------------------------- the built-in defaults


def test_a_fresh_person_sees_every_project_and_the_time_of_their_department_only(
    world: World,
) -> None:
    """[§6 rule 3, D-013] Defaults: Viewer everywhere, Hours viewer in the own department."""
    anna = world.person("Anna", "quality")
    principal = world.principal(anna)
    assert world.allowed_nodes(principal, Permission.PROJECT_VIEW) == set(ALL_NODES)
    assert world.allowed_nodes(principal, Permission.HOURS_VIEW) == STL_BRANCH
    for permission in (
        Permission.PROJECT_EDIT,
        Permission.PROJECT_COMMENT,
        Permission.PROJECT_DELETE,
        Permission.PLAN_MANAGE,
        Permission.ORG_MANAGE,
        Permission.USERS_MANAGE,
    ):
        assert world.allowed_nodes(principal, permission) == set(), permission


def test_the_anonymous_visitor_has_nothing_by_default(world: World) -> None:
    visitor = anonymous_principal(world.session)
    assert visitor.is_anonymous
    for permission in Permission:
        assert world.allowed_nodes(visitor, permission) == set()
        assert not visitor.can_somewhere(permission)
    with pytest.raises(AuthenticationRequiredError):
        visitor.require(Permission.PROJECT_VIEW, world.nodes["stl"].id)


def test_a_signed_in_person_who_may_not_gets_403_not_401(world: World) -> None:
    principal = world.principal(world.person("Anna", "quality"))
    with pytest.raises(PermissionDeniedError, match=r"project.edit"):
        principal.require(Permission.PROJECT_EDIT, world.nodes["quality"].id)
    principal.require(Permission.PROJECT_VIEW, world.nodes["quality"].id)  # allowed: no error


# ---------------------------------------------------------------- personas


def test_a_project_administrator_on_a_branch_edits_that_branch_only(world: World) -> None:
    """In scope: the node and its child. Out: its ancestor, its sibling, other departments."""
    padmin = world.person("Pia", "coatings", ("project_admin", world.node_scope("quality")))
    principal = world.principal(padmin)
    expected = {"quality", "lab"}
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == expected
    assert world.allowed_nodes(principal, Permission.PROJECT_COMMENT) == expected
    assert world.allowed_nodes(principal, Permission.PLAN_MANAGE) == expected
    assert world.allowed_nodes(principal, Permission.PROJECT_DELETE) == set()
    assert world.allowed_nodes(principal, Permission.PROJECT_VIEW) == set(ALL_NODES)
    assert world.allowed_nodes(principal, Permission.HOURS_VIEW) == RD_BRANCH  # her department
    assert principal.can_somewhere(Permission.PROJECT_EDIT)
    assert not principal.can(Permission.PROJECT_EDIT)  # not everywhere


def test_a_project_administrator_everywhere_edits_every_branch(world: World) -> None:
    padmin = world.person("Paul", "staff", ("project_admin", Scope.everywhere()))
    principal = world.principal(padmin)
    for permission in (Permission.PROJECT_EDIT, Permission.PROJECT_COMMENT, Permission.PLAN_MANAGE):
        assert world.allowed_nodes(principal, permission) == set(ALL_NODES)
        assert principal.can(permission)
    assert world.allowed_nodes(principal, Permission.PROJECT_DELETE) == set()
    assert world.allowed_nodes(principal, Permission.USERS_MANAGE) == set()


def test_an_hours_viewer_on_a_branch_sees_the_hours_of_that_branch(world: World) -> None:
    """Placed in Staff (no department): the own-department default grant applies nowhere."""
    head = world.person("Henk", "staff", ("hours_viewer", world.node_scope("stl")))
    principal = world.principal(head)
    assert principal.department_id is None
    assert world.allowed_nodes(principal, Permission.HOURS_VIEW) == STL_BRANCH
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == set()


def test_an_administrator_may_do_everything_everywhere(world: World) -> None:
    root = world.person("Ada", "staff", ("admin", Scope.everywhere()))
    principal = world.principal(root)
    for permission in Permission:
        assert principal.can(permission), permission
        if permission.is_scoped:
            assert world.allowed_nodes(principal, permission) == set(ALL_NODES), permission


def test_an_administrator_on_one_branch_has_no_administration(world: World) -> None:
    """[§6 rule 1] A global permission counts only when assigned globally."""
    local = world.person("Lars", "quality", ("admin", world.node_scope("stl")))
    principal = world.principal(local)
    assert world.allowed_nodes(principal, Permission.PROJECT_DELETE) == STL_BRANCH
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == STL_BRANCH
    assert not principal.can(Permission.USERS_MANAGE)
    assert not principal.can(Permission.ORG_MANAGE)
    assert not principal.can_somewhere(Permission.USERS_MANAGE)


def test_a_person_forced_to_change_their_password_can_do_nothing(world: World) -> None:
    person = world.person("Newbie", "quality", ("project_admin", Scope.everywhere()))
    person.must_change_password = True
    principal = world.principal(person)
    for permission in Permission:
        assert not principal.can(permission, world.nodes["quality"].id)
        assert not principal.can_somewhere(permission)
        assert principal.reach(permission).nowhere
    with pytest.raises(PasswordChangeRequiredError):
        principal.require(Permission.PROJECT_VIEW)
    assert AccessPolicy(principal).can_see_hours_of(person.id, None) is False


def test_system_accounts_are_not_people(world: World) -> None:
    kinds = {u.username: u.kind for u in world.session.scalars(select(User)) if u.username}
    assert kinds["admin"] is UserKind.SYSTEM
    assert kinds["anonymous"] is UserKind.SYSTEM
    admin = world.session.scalar(select(User).where(User.username == "admin"))
    assert admin is not None
    principal = principal_for_user(world.session, admin)
    assert principal.is_system
    assert principal.can(Permission.USERS_MANAGE)
    assert principal.department_id is None  # no org node


# ---------------------------------------------------------------- own department


def own_department_of(world: World, person: User) -> str | None:
    department = world.principal(person).department_id
    names = {node.id: key for key, node in world.nodes.items()}
    return names.get(department) if department else None


def test_the_own_department_follows_flags_and_the_person(world: World) -> None:
    """Flag on the person's node, on an ancestor, none; then the person moves, the flag moves."""
    lab, quality, stl, rd = (world.nodes[n] for n in ("lab", "quality", "stl", "rd"))
    person = world.person("Lisa", "lab", ("project_admin", Scope.own_department()))
    world.session.flush()

    assert own_department_of(world, person) == "stl"  # the flag is on an ancestor (grand-parent)
    principal = world.principal(person)
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == STL_BRANCH
    assert world.allowed_nodes(principal, Permission.HOURS_VIEW) == STL_BRANCH

    quality.is_department = True  # a nearer flag wins
    assert own_department_of(world, person) == "quality"
    principal = world.principal(person)
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == {"quality", "lab"}

    lab.is_department = True  # on the person's own node
    assert own_department_of(world, person) == "lab"
    assert world.allowed_nodes(world.principal(person), Permission.PROJECT_EDIT) == {"lab"}

    for node in (lab, quality, stl):  # no flag anywhere on the path: no department
        node.is_department = False
    assert own_department_of(world, person) is None
    principal = world.principal(person)
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == set()
    assert world.allowed_nodes(principal, Permission.HOURS_VIEW) == set()
    assert world.allowed_nodes(principal, Permission.PROJECT_VIEW) == set(ALL_NODES)  # default

    stl.is_department = True  # the flag moves...
    assert own_department_of(world, person) == "stl"
    person.org_node_id = world.nodes["coatings"].id  # ...and the person moves
    assert own_department_of(world, person) == "rd"
    principal = world.principal(person)
    assert world.allowed_nodes(principal, Permission.PROJECT_EDIT) == RD_BRANCH
    assert rd.is_department


# ---------------------------------------------------------------- implicit rights (D-014)


def test_a_coordinator_and_members_have_implicit_rights_on_their_project(world: World) -> None:
    coordinator = world.person("Cora", "coatings")
    member = world.person("Mo", "coatings")
    outsider = world.person("Otto", "coatings")
    project = make_project(
        world.session,
        number=4102,
        org=world.nodes["stl"],
        coordinator=coordinator,
        members=(member,),
    )
    node = world.nodes["stl"].id

    def policy(person: User) -> AccessPolicy:
        return AccessPolicy(world.principal(person))

    def rights(person: User) -> set[Permission]:
        return {
            p
            for p in (
                Permission.PROJECT_VIEW,
                Permission.PROJECT_EDIT,
                Permission.PROJECT_COMMENT,
                Permission.PROJECT_DELETE,
                Permission.PLAN_MANAGE,
            )
            if policy(person).can_on_project(
                p,
                node_id=node,
                coordinator_id=project.coordinator_id,
                member_ids={coordinator.id, member.id},
            )
        }

    assert rights(coordinator) == {
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_COMMENT,
    }
    assert rights(member) == {Permission.PROJECT_VIEW, Permission.PROJECT_COMMENT}
    assert rights(outsider) == {Permission.PROJECT_VIEW}  # the default Viewer, nothing more


def test_implicit_rights_do_not_survive_a_forced_password_change(world: World) -> None:
    coordinator = world.person("Cora", "coatings")
    coordinator.must_change_password = True
    policy = AccessPolicy(world.principal(coordinator))
    assert not policy.can_on_project(
        Permission.PROJECT_EDIT, node_id=world.nodes["stl"].id, coordinator_id=coordinator.id
    )


# ---------------------------------------------------------------- query filters


def visible_numbers(world: World, person: User, permission: Permission) -> set[int]:
    policy = AccessPolicy(world.principal(person))
    rows = world.session.execute(select(Project.number).where(policy.project_filter(permission)))
    return {number for (number,) in rows}


@pytest.fixture
def projects(world: World) -> dict[str, int]:
    """One project per node, numbered 1..8; coordinated by a person of Staff."""
    boss = world.person("Boss", "staff")
    numbers: dict[str, int] = {}
    for index, name in enumerate(ALL_NODES, start=1):
        make_project(world.session, number=index, org=world.nodes[name], coordinator=boss)
        numbers[name] = index
    return numbers


def test_lists_only_contain_what_the_caller_may_see(world: World, projects: dict[str, int]) -> None:
    anna = world.person("Anna", "quality")
    assert visible_numbers(world, anna, Permission.PROJECT_VIEW) == set(projects.values())
    assert visible_numbers(world, anna, Permission.PROJECT_EDIT) == set()

    padmin = world.person("Pia", "coatings", ("project_admin", world.node_scope("quality")))
    assert visible_numbers(world, padmin, Permission.PROJECT_EDIT) == {
        projects["quality"],
        projects["lab"],
    }


def test_the_coordinator_and_members_see_their_project_even_when_defaults_are_gone(
    world: World, projects: dict[str, int]
) -> None:
    for grant in world.session.scalars(select(DefaultGrant)):
        world.session.delete(grant)  # nobody is a Viewer by default any more
    world.session.flush()
    person = world.person("Cora", "coatings")
    assert visible_numbers(world, person, Permission.PROJECT_VIEW) == set()
    mine = make_project(world.session, number=99, org=world.nodes["rd"], coordinator=person)
    shared = make_project(
        world.session,
        number=98,
        org=world.nodes["stl"],
        coordinator=world.person("Boss 2", "staff"),
        members=(person,),
    )
    assert mine.number == 99
    assert shared.number == 98
    assert visible_numbers(world, person, Permission.PROJECT_VIEW) == {99, 98}
    assert visible_numbers(world, person, Permission.PROJECT_EDIT) == {99}  # coordinators edit
    assert visible_numbers(world, person, Permission.PROJECT_COMMENT) == {99, 98}


def test_after_removing_the_default_viewer_grant_projects_disappear(
    world: World, projects: dict[str, int]
) -> None:
    anna = world.person("Anna", "quality")
    assert len(visible_numbers(world, anna, Permission.PROJECT_VIEW)) == 8
    viewer = world.role("viewer")
    for grant in world.session.scalars(
        select(DefaultGrant).where(
            DefaultGrant.audience == Audience.SIGNED_IN, DefaultGrant.role_id == viewer.id
        )
    ):
        world.session.delete(grant)
    world.session.flush()
    assert visible_numbers(world, anna, Permission.PROJECT_VIEW) == set()
    # An explicit assignment brings back just what it says.
    assignment = RoleAssignment(user_id=anna.id, role_id=viewer.id)
    assignment.scope = world.node_scope("rd")
    world.session.add(assignment)
    assert visible_numbers(world, anna, Permission.PROJECT_VIEW) == {
        projects["rd"],
        projects["coatings"],
    }


def test_the_anonymous_floor_applies_to_everyone(world: World, projects: dict[str, int]) -> None:
    """[§6 rule 3] Giving visitors Viewer on R&D gives every signed-in person at least that."""
    for grant in world.session.scalars(select(DefaultGrant)):
        world.session.delete(grant)
    grant = DefaultGrant(audience=Audience.ANONYMOUS, role_id=world.role("viewer").id)
    grant.scope = world.node_scope("rd")
    world.session.add(grant)
    world.session.flush()
    anna = world.person("Anna", "quality")
    visitor = anonymous_principal(world.session)
    assert world.allowed_nodes(visitor, Permission.PROJECT_VIEW) == RD_BRANCH
    assert visible_numbers(world, anna, Permission.PROJECT_VIEW) == {
        projects["rd"],
        projects["coatings"],
    }


def test_time_is_visible_to_its_owner_and_to_hours_viewers_only(world: World) -> None:
    anna = world.person("Anna", "quality")
    bram = world.person("Bram", "process")  # same department
    carl = world.person("Carl", "coatings")  # another department
    nobody = world.person("Nobody", None)  # no org node at all

    def seen_by(viewer: User) -> set[str]:
        policy = AccessPolicy(world.principal(viewer))
        rows = world.session.scalars(select(User.name).where(policy.people_hours_filter()))
        return {name for name in rows if name in {"Anna", "Bram", "Carl", "Nobody"}}

    assert seen_by(anna) == {"Anna", "Bram"}  # their department, which includes themselves
    assert seen_by(carl) == {"Carl"}
    assert seen_by(nobody) == {"Nobody"}  # always their own
    head = world.person("Head", "staff", ("hours_viewer", Scope.everywhere()))
    assert {"Anna", "Bram", "Carl", "Nobody"} <= seen_by(head)

    policy = AccessPolicy(world.principal(anna))
    assert policy.can_see_hours_of(anna.id, anna.org_node_id)
    assert policy.can_see_hours_of(bram.id, bram.org_node_id)
    assert not policy.can_see_hours_of(carl.id, carl.org_node_id)
    assert not policy.can_see_hours_of(nobody.id, None)
    assert AccessPolicy(world.principal(head)).can_see_hours_of(nobody.id, None)  # global grant


def test_the_anonymous_visitor_sees_no_time_and_no_projects(
    world: World, projects: dict[str, int]
) -> None:
    visitor = AccessPolicy(anonymous_principal(world.session))
    assert not list(world.session.scalars(select(User.id).where(visitor.people_hours_filter())))
    assert not list(world.session.scalars(select(Project.id).where(visitor.project_filter())))
    assert not visitor.can_see_hours_of(1, None)
    assert len(projects) == 8
