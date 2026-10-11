"""The org tree, scopes, grants and reach: the pure decisions behind §6."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from momato.domain.access import (
    BUILTIN_ROLE_PERMISSIONS,
    DEFAULT_GRANTS,
    PERMISSION_DESCRIPTIONS,
    SCOPED_PERMISSIONS,
    TOKEN_PERMISSIONS,
    Audience,
    BuiltinRole,
    Grant,
    GrantSet,
    Permission,
    Reach,
    Scope,
    ScopeKind,
    TokenScope,
)
from momato.domain.orgtree import OrgNodeRef, OrgTree

#   1 root
#   ├─ 2 STL (department)
#   │   ├─ 3 Quality
#   │   │   └─ 4 Lab
#   │   └─ 5 Process
#   ├─ 6 R&D (department)
#   │   └─ 7 Coatings
#   └─ 8 Staff (not a department)
ROOT, STL, QUALITY, LAB, PROCESS, RD, COATINGS, STAFF = range(1, 9)
TREE = OrgTree(
    [
        OrgNodeRef(ROOT, None, False),
        OrgNodeRef(STL, ROOT, True),
        OrgNodeRef(QUALITY, STL, False),
        OrgNodeRef(LAB, QUALITY, False),
        OrgNodeRef(PROCESS, STL, False),
        OrgNodeRef(RD, ROOT, True),
        OrgNodeRef(COATINGS, RD, False),
        OrgNodeRef(STAFF, ROOT, False),
    ]
)
EVERYWHERE = Scope.everywhere()


def grants(*pairs: tuple[Permission, Scope]) -> GrantSet:
    return GrantSet([Grant(p, s) for p, s in pairs])


# ---------------------------------------------------------------- the tree


def test_ancestors_run_from_the_node_to_the_root() -> None:
    assert TREE.ancestors_or_self(LAB) == [LAB, QUALITY, STL, ROOT]
    assert TREE.ancestors_or_self(ROOT) == [ROOT]
    assert TREE.ancestors_or_self(99) == []


def test_the_department_is_the_nearest_flagged_node_up_the_path() -> None:
    """[D-006]"""
    assert TREE.department_of(LAB) == STL
    assert TREE.department_of(STL) == STL  # a flagged node is its own department
    assert TREE.department_of(COATINGS) == RD
    assert TREE.department_of(STAFF) is None
    assert TREE.department_of(ROOT) is None
    assert TREE.department_of(None) is None
    assert TREE.department_of(99) is None


def test_a_nearer_flag_wins() -> None:
    nested = OrgTree(
        [
            OrgNodeRef(1, None, False),
            OrgNodeRef(2, 1, True),
            OrgNodeRef(3, 2, True),
            OrgNodeRef(4, 3, False),
        ]
    )
    assert nested.department_of(4) == 3
    assert nested.department_of(2) == 2


def test_subtrees() -> None:
    assert TREE.subtree(STL) == {STL, QUALITY, LAB, PROCESS}
    assert TREE.subtree(LAB) == {LAB}
    assert TREE.subtree(ROOT) == TREE.ids
    assert TREE.subtree(99) == frozenset()
    assert TREE.covered_by([LAB, RD]) == {LAB, RD, COATINGS}
    assert TREE.covered_by([]) == frozenset()
    assert TREE.is_within(LAB, frozenset({STL}))
    assert not TREE.is_within(STL, frozenset({LAB}))
    assert len(TREE) == 8
    assert STL in TREE
    assert 99 not in TREE


def test_a_cycle_cannot_loop_forever() -> None:
    cyclic = OrgTree([OrgNodeRef(1, 2, False), OrgNodeRef(2, 1, False)])
    assert cyclic.ancestors_or_self(1) == [1, 2]
    assert cyclic.subtree(1) == {1, 2}


# ---------------------------------------------------------------- scopes


def test_scope_keys_are_stable_text() -> None:
    assert Scope.everywhere().key == "global"
    assert Scope.node(7).key == "node:7"
    assert Scope.own_department().key == "own_department"


def test_a_scope_needs_a_node_exactly_when_it_is_a_node_scope() -> None:
    with pytest.raises(ValueError, match="node id"):
        Scope(ScopeKind.NODE)
    with pytest.raises(ValueError, match="node id"):
        Scope(ScopeKind.GLOBAL, 3)


# ---------------------------------------------------------------- grants


def test_a_node_grant_covers_its_whole_branch_but_not_its_surroundings() -> None:
    """[§6 rule 1] In scope: the node and below. Out: ancestor, sibling, other branches."""
    held = grants((Permission.PROJECT_EDIT, Scope.node(QUALITY)))
    allowed = {n for n in TREE.ids if held.allows(Permission.PROJECT_EDIT, n, TREE)}
    assert allowed == {QUALITY, LAB}


def test_a_global_grant_covers_everything_and_the_unplaced() -> None:
    held = grants((Permission.PROJECT_VIEW, EVERYWHERE))
    assert all(held.allows(Permission.PROJECT_VIEW, n, TREE) for n in TREE.ids)
    assert held.allows(Permission.PROJECT_VIEW, None, TREE)
    assert held.reach(Permission.PROJECT_VIEW, TREE) == Reach(everywhere=True)


def test_a_scoped_grant_never_answers_the_question_everywhere() -> None:
    held = grants((Permission.PROJECT_VIEW, Scope.node(STL)))
    assert not held.allows(Permission.PROJECT_VIEW, None, TREE)
    assert held.allows_somewhere(Permission.PROJECT_VIEW, TREE)


def test_unscoped_permissions_count_only_when_granted_globally() -> None:
    """[§6 rule 1] org.manage on one node is nothing."""
    held = grants(
        (Permission.ORG_MANAGE, Scope.node(STL)), (Permission.USERS_MANAGE, Scope.own_department())
    )
    for permission in (Permission.ORG_MANAGE, Permission.USERS_MANAGE):
        assert not held.allows(permission, STL, TREE)
        assert not held.allows(permission, None, TREE)
        assert not held.allows_somewhere(permission, TREE)
        assert held.reach(permission, TREE).nowhere
    assert grants((Permission.ORG_MANAGE, EVERYWHERE)).allows(Permission.ORG_MANAGE, None, TREE)


def test_own_department_resolves_to_the_holders_department() -> None:
    """[§6 rule 2]"""
    held = GrantSet([Grant(Permission.HOURS_VIEW, Scope.own_department())], own_department=STL)
    allowed = {n for n in TREE.ids if held.allows(Permission.HOURS_VIEW, n, TREE)}
    assert allowed == {STL, QUALITY, LAB, PROCESS}
    assert held.reach(Permission.HOURS_VIEW, TREE) == Reach(False, frozenset({STL}))


def test_own_department_without_a_department_applies_nowhere() -> None:
    held = GrantSet([Grant(Permission.HOURS_VIEW, Scope.own_department())], own_department=None)
    assert not any(held.allows(Permission.HOURS_VIEW, n, TREE) for n in TREE.ids)
    assert not held.allows_somewhere(Permission.HOURS_VIEW, TREE)
    assert held.reach(Permission.HOURS_VIEW, TREE).nowhere


def test_grants_of_other_permissions_do_not_leak() -> None:
    held = grants((Permission.PROJECT_VIEW, EVERYWHERE))
    assert not held.allows(Permission.PROJECT_EDIT, STL, TREE)
    assert not held.allows_somewhere(Permission.PLAN_MANAGE, TREE)


def test_reach_ignores_nodes_that_no_longer_exist() -> None:
    held = grants(
        (Permission.PROJECT_VIEW, Scope.node(99)), (Permission.PROJECT_VIEW, Scope.node(RD))
    )
    assert held.reach(Permission.PROJECT_VIEW, TREE).node_ids == {RD}
    assert not grants((Permission.PROJECT_VIEW, Scope.node(99))).allows_somewhere(
        Permission.PROJECT_VIEW, TREE
    )


def test_a_grant_set_can_be_iterated_and_counted() -> None:
    held = grants((Permission.PROJECT_VIEW, EVERYWHERE), (Permission.HOURS_VIEW, Scope.node(STL)))
    assert len(held) == 2
    assert {g.permission for g in held} == {Permission.PROJECT_VIEW, Permission.HOURS_VIEW}


# ---------------------------------------------------------------- the catalogue


def test_the_built_in_roles_follow_the_table_of_section_6() -> None:
    assert BuiltinRole.VIEWER.permissions == {Permission.PROJECT_VIEW}
    assert BuiltinRole.PROJECT_ADMIN.permissions == {
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_COMMENT,
        Permission.PLAN_MANAGE,
    }
    assert BuiltinRole.HOURS_VIEWER.permissions == {Permission.HOURS_VIEW}
    assert BuiltinRole.ADMIN.permissions == set(Permission)
    assert Permission.PROJECT_DELETE not in BuiltinRole.PROJECT_ADMIN.permissions  # admins only
    assert [r.label for r in BuiltinRole] == [
        "Viewer",
        "Project administrator",
        "Hours viewer",
        "Administrator",
    ]


def test_scoped_and_global_permissions() -> None:
    assert {p for p in Permission if p.is_scoped} == SCOPED_PERMISSIONS
    assert not Permission.ORG_MANAGE.is_scoped
    assert not Permission.USERS_MANAGE.is_scoped
    assert set(PERMISSION_DESCRIPTIONS) == set(Permission)
    assert set(BUILTIN_ROLE_PERMISSIONS) == set(BuiltinRole)


def test_default_grants_are_the_decision_d_013() -> None:
    """Signed-in people: Viewer everywhere and Hours viewer in their own department; visitors:
    nothing (the tool requires a login)."""
    assert DEFAULT_GRANTS[Audience.SIGNED_IN] == [
        (BuiltinRole.VIEWER, Scope.everywhere()),
        (BuiltinRole.HOURS_VIEWER, Scope.own_department()),
    ]
    assert DEFAULT_GRANTS[Audience.ANONYMOUS] == []


def test_tokens_never_administer() -> None:
    """[TOK-1] Read-only keeps view permissions; read-write all but org and users management."""
    assert TokenScope.READ.permissions == {Permission.PROJECT_VIEW, Permission.HOURS_VIEW}
    assert TokenScope.WRITE.permissions == set(Permission) - {
        Permission.ORG_MANAGE,
        Permission.USERS_MANAGE,
    }
    assert set(TOKEN_PERMISSIONS) == set(TokenScope)


# ---------------------------------------------------------------- properties


nodes = st.sampled_from(sorted(TREE.ids))


@given(st.sets(nodes), nodes)
def test_a_node_is_covered_exactly_when_an_ancestor_or_it_is_a_root(
    roots: set[int], node: int
) -> None:
    held = GrantSet([Grant(Permission.PROJECT_VIEW, Scope.node(r)) for r in roots])
    expected = any(a in roots for a in TREE.ancestors_or_self(node))
    assert held.allows(Permission.PROJECT_VIEW, node, TREE) is expected
    assert (node in TREE.covered_by(roots)) is expected


@given(st.sets(nodes), st.sets(nodes))
def test_more_grants_never_allow_less(first: set[int], extra: set[int]) -> None:
    small = GrantSet([Grant(Permission.PROJECT_EDIT, Scope.node(r)) for r in first])
    large = GrantSet([Grant(Permission.PROJECT_EDIT, Scope.node(r)) for r in first | extra])
    for node in TREE.ids:
        if small.allows(Permission.PROJECT_EDIT, node, TREE):
            assert large.allows(Permission.PROJECT_EDIT, node, TREE)
