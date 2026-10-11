"""The organisation tree as the rules see it: parents, department flags, subtrees (D-006, §6).

Pure and immutable; built from the `org_nodes` rows once per request. Permissions on a node cover
its whole subtree, and a person's department is the nearest flagged node on the path from their
node up to the root.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrgNodeRef:
    id: int
    parent_id: int | None
    is_department: bool


class OrgTree:
    def __init__(self, nodes: Iterable[OrgNodeRef] = ()) -> None:
        self._nodes = {n.id: n for n in nodes}
        children: dict[int, list[int]] = defaultdict(list)
        for node in self._nodes.values():
            if node.parent_id is not None:
                children[node.parent_id].append(node.id)
        self._children = dict(children)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    @property
    def ids(self) -> frozenset[int]:
        return frozenset(self._nodes)

    def ancestors_or_self(self, node_id: int) -> list[int]:
        """The node, its parent, ... up to the root; empty for an unknown node."""
        path: list[int] = []
        seen: set[int] = set()
        current: int | None = node_id
        while current is not None and current in self._nodes and current not in seen:
            seen.add(current)  # a cycle (never produced by the editor) cannot loop forever
            path.append(current)
            current = self._nodes[current].parent_id
        return path

    def department_of(self, node_id: int | None) -> int | None:
        """The nearest flagged node on the path from `node_id` up to the root, or None."""
        if node_id is None:
            return None
        return next(
            (n for n in self.ancestors_or_self(node_id) if self._nodes[n].is_department), None
        )

    def subtree(self, node_id: int) -> frozenset[int]:
        """The node and everything below it; empty for an unknown node."""
        if node_id not in self._nodes:
            return frozenset()
        found: set[int] = set()
        pending = [node_id]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(self._children.get(current, ()))
        return frozenset(found)

    def covered_by(self, roots: Iterable[int]) -> frozenset[int]:
        """Every node in the subtree of any of `roots`."""
        covered: set[int] = set()
        for root in roots:
            covered |= self.subtree(root)
        return frozenset(covered)

    def is_within(self, node_id: int, roots: frozenset[int]) -> bool:
        """Whether `node_id` lies in the subtree of one of `roots`."""
        return any(a in roots for a in self.ancestors_or_self(node_id))
