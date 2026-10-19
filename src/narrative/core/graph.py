"""One canonical document with defensive projections and explicit mutation."""

import networkx as nx

from .schema import CanonStatus, Constraint, Edge, Finding, Node, Project


class GraphError(ValueError):
    pass


class StoryGraph:
    def __init__(self, document: Project):
        self._document = Project.model_validate(document.model_dump(mode="json", warnings=False))
        self._rebuild()

    def _rebuild(self):
        self._nodes = {n.id: n for n in self._document.nodes}
        self._edges = {e.id: e for e in self._document.edges}
        self._graph = nx.MultiDiGraph()
        self._graph.add_nodes_from(self._nodes)
        for edge in self._edges.values():
            self._graph.add_edge(edge.source, edge.target, key=edge.id, kind=edge.kind)

    @property
    def document(self) -> Project:
        return self._document.model_copy(deep=True)

    @property
    def nodes(self) -> dict[str, Node]:
        return {key: n.model_copy(deep=True) for key, n in self._nodes.items()}

    @property
    def edges(self) -> dict[str, Edge]:
        return {key: e.model_copy(deep=True) for key, e in self._edges.items()}

    def get(self, node_id: str) -> Node:
        if node_id not in self._nodes:
            raise GraphError(f"Unknown node: {node_id}")
        return self._nodes[node_id].model_copy(deep=True)

    def incoming(self, node_id: str) -> list[Edge]:
        return [e.model_copy(deep=True) for e in self._edges.values() if e.target == node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e.model_copy(deep=True) for e in self._edges.values() if e.source == node_id]

    def clone(self) -> "StoryGraph":
        return StoryGraph(self._document)

    def constraints_for(self, node_id: str) -> list[Constraint]:
        """Resolve project and ancestor commitments without duplicating canon."""
        current = self.get(node_id)
        constraints = list(self._document.constraints)
        seen = set()
        while current.id not in seen:
            seen.add(current.id)
            constraints.extend(current.hard_constraints)
            if not current.parent_id or current.parent_id not in self._nodes:
                break
            current = self.get(current.parent_id)
        unique = []
        for constraint in constraints:
            if constraint not in unique:
                unique.append(constraint.model_copy(deep=True))
        return unique

    def add_node(self, node: Node):
        node = Node.model_validate(node.model_dump(mode="json", warnings=False))
        if node.id in self._nodes:
            raise GraphError(f"Duplicate node: {node.id}")
        self._document.nodes.append(node.model_copy(deep=True))
        self._rebuild()

    def add_edge(self, edge: Edge):
        edge = Edge.model_validate(edge.model_dump(mode="json", warnings=False))
        if edge.id in self._edges:
            raise GraphError(f"Duplicate edge: {edge.id}")
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise GraphError(f"Dangling edge: {edge.id}")
        self._document.edges.append(edge.model_copy(deep=True))
        self._rebuild()

    def update_node(self, node_id: str, changes: dict, authorized: bool = False):
        node = self.get(node_id)
        if node.locked and not authorized:
            raise GraphError(f"Locked canon requires explicit authorization: {node_id}")
        if changes.get("id", node_id) != node_id:
            raise GraphError("Node IDs cannot change")
        new_status = changes.get("status", node.status)
        if node.status != CanonStatus.CANON and new_status == CanonStatus.CANON and not authorized:
            raise GraphError("Promoting a proposal to canon requires explicit authorization")
        payload = node.model_dump()
        payload.update(changes)
        payload["version"] = node.version + 1
        replacement = Node.model_validate(payload)
        self._document.nodes = [replacement if n.id == node_id else n for n in self._document.nodes]
        self._rebuild()

    def validate(self) -> list[Finding]:
        findings = []
        hierarchy = nx.DiGraph()
        hierarchy.add_nodes_from(self._nodes)
        for node in self._nodes.values():
            if node.parent_id:
                if node.parent_id not in self._nodes:
                    findings.append(Finding(code="MISSING_PARENT", message="Parent does not exist", node_ids=[node.id]))
                else:
                    hierarchy.add_edge(node.parent_id, node.id)
                    if node.level <= self._nodes[node.parent_id].level:
                        findings.append(Finding(code="DETAIL_LEVEL", message="Child level must exceed parent level", node_ids=[node.id, node.parent_id]))
        if not nx.is_directed_acyclic_graph(hierarchy):
            findings.append(Finding(code="HIERARCHY_CYCLE", message="Hierarchy contains a cycle"))
        for edge in self._edges.values():
            if edge.source not in self._nodes or edge.target not in self._nodes:
                findings.append(Finding(code="DANGLING_EDGE", message=f"Invalid endpoint on {edge.id}", node_ids=[edge.source, edge.target]))
        for node in self._nodes.values():
            if node.transition:
                for participant in node.transition.participants:
                    if participant not in self._nodes:
                        findings.append(Finding(code="MISSING_PARTICIPANT", message=f"Unknown participant {participant}", node_ids=[node.id]))
            if node.status == CanonStatus.CANON:
                if node.kind == "Hypothesis" and node.transition:
                    findings.append(Finding(code="HYPOTHESIS_TRANSITION", message="Hypothetical content cannot execute as actual canon; use a canonical observation event for belief changes", node_ids=[node.id]))
                inherited = self.constraints_for(node.id)
                seen_constraints = {}
                for constraint in inherited:
                    key = (constraint.scope, constraint.key)
                    if key in seen_constraints and seen_constraints[key] != constraint.expected:
                        findings.append(Finding(code="CONSTRAINT_CONFLICT", message=f"Conflicting commitments for {constraint.key}", node_ids=[node.id], evidence=[constraint.id]))
                    seen_constraints[key] = constraint.expected
                    if (constraint.scope == "design" and constraint.key in node.attributes
                            and node.attributes[constraint.key] != constraint.expected):
                        findings.append(Finding(code="DESIGN_CONSTRAINT", message=constraint.description or constraint.id, node_ids=[node.id], evidence=[constraint.id]))
        return findings
