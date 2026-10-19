"""Finite top-down decomposition into reviewable PROPOSED graph branches."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field, JsonValue

from .core.graph import StoryGraph
from .core.schema import CanonStatus, Constraint, Edge, EdgeType, Node, NodeType, Provenance, Transition
from .memory import Budget, BudgetExceeded, Telemetry, retrieve
from .providers import MockProvider, OutputRecord, Provider, ProviderOutputError, structured_generate


class ProposedChild(OutputRecord):
    label: str = Field(min_length=1, max_length=500)
    kind: NodeType = NodeType.SCENE
    purpose: str = Field(min_length=1, max_length=2000)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    transition: Transition | None = None


class Decomposition(OutputRecord):
    children: list[ProposedChild] = Field(min_length=1, max_length=16)
    information_gain: float = Field(ge=0, le=1, allow_inf_nan=False)
    feedback: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(min_length=1, max_length=2000)


@dataclass
class RefinementResult:
    graph: StoryGraph
    children: list[str] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    telemetry: Telemetry = field(default_factory=Telemetry)
    stopped_reason: str = "completed"

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {"document": self.graph.document.model_dump(mode="json"),
                "children": self.children, "checkpoints": self.checkpoints,
                "feedback": self.feedback, "telemetry": self.telemetry.model_dump(),
                "stopped_reason": self.stopped_reason,
                "limitations": ["Proposals require review before canonical state simulation",
                                "Provider information gain is a declared estimate, not measured literary quality"]}


def _inherited_constraints(graph: StoryGraph, node: Node) -> list[Constraint]:
    inherited = list(graph.document.constraints)
    nodes = graph.nodes
    seen: set[str] = set()
    current: Node | None = node
    while current is not None and current.id not in seen:
        seen.add(current.id)
        inherited.extend(current.hard_constraints)
        current = nodes.get(current.parent_id)
    unique: dict[str, Constraint] = {}
    for constraint in inherited:
        if constraint.id in unique and unique[constraint.id] != constraint:
            raise ValueError(f"Conflicting inherited constraint definition: {constraint.id}")
        unique[constraint.id] = constraint.model_copy(deep=True)
    by_key: dict[tuple[str, str], Constraint] = {}
    for constraint in unique.values():
        key = (constraint.scope, constraint.key)
        if key in by_key and by_key[key].expected != constraint.expected:
            raise ValueError(f"Conflicting inherited hard constraints for {constraint.key}")
        by_key[key] = constraint
    return list(unique.values())


def _importance(node: Node) -> float:
    """Transparent scheduling heuristic, not a narrative quality score."""
    return sum(bool(node.attributes.get(key)) for key in
               ("critical", "thematic_pivot", "major_revelation")) + \
        bool(node.transition and node.transition.irreversible)


def refine(graph: StoryGraph, node_id: str, depth: int = 2, *, max_nodes: int = 12,
           min_information_gain: float = 0.05, provider: Provider | None = None,
           budget: Budget | None = None, token_budget: int = 12_000,
           max_retries: int = 1) -> RefinementResult:
    """Return an isolated branch; never change or promote the source graph.

    Finite depth, nodes, calls, byte-unit context/output budgets, and declared
    information gain all stop recursion. A failed parent decomposition is atomic.
    Feedback proposes ancestor changes as text and never applies them.
    """
    if not 0 <= depth <= 9 or not 0 <= max_nodes <= 1000:
        raise ValueError("depth must be in 0..9 and max_nodes in 0..1000")
    if not 0 <= min_information_gain <= 1:
        raise ValueError("Information gain threshold must be in 0..1")
    original = graph.get(node_id)
    errors = [finding for finding in graph.validate() if finding.severity == "error"]
    if errors:
        raise ValueError(f"Cannot refine invalid graph: {errors[0].message}")
    provider = provider if provider is not None else MockProvider()
    budget = budget if budget is not None else Budget()
    result = RefinementResult(graph.clone(), telemetry=Telemetry(provider=provider.name))
    started = time.perf_counter()
    retrieved_ids: set[str] = set()
    frontier: list[tuple[str, int]] = [(original.id, 0)]
    while frontier:
        frontier.sort(key=lambda item: (-_importance(result.graph.get(item[0])), item[1], item[0]))
        parent_id, relative_depth = frontier.pop(0)
        parent = result.graph.get(parent_id)
        if relative_depth >= depth or parent.level >= 9:
            result.checkpoints.append({"node_id": parent_id, "status": "stopped", "reason": "depth_limit"})
            continue
        if len(result.children) >= max_nodes:
            result.stopped_reason = "node_limit"
            break
        constraints = _inherited_constraints(result.graph, parent)
        context = retrieve(result.graph, parent_id, token_budget=token_budget)
        retrieved_ids.update(context.node_ids)
        if context.overflow:
            result.stopped_reason = "context_overflow"
            result.checkpoints.append({"node_id": parent_id, "status": "blocked",
                                       "reason": "context_overflow", "warnings": context.warnings})
            break
        remaining = max_nodes - len(result.children)
        request = {"operation": "proposed_decomposition", "node": parent.model_dump(mode="json"),
                   "context": context.model_dump(),
                   "constraints": [item.model_dump(mode="json") for item in constraints],
                   "max_children": min(4 if _importance(parent) >= 2 else 2, remaining),
                   "instructions": "Return proposed details and unresolved ancestor feedback; no promotion to canon"}
        try:
            proposal = structured_generate(provider, request, Decomposition, budget=budget,
                                           telemetry=result.telemetry, max_retries=max_retries)
        except (BudgetExceeded, ProviderOutputError) as exc:
            result.stopped_reason = "budget_exhausted" if isinstance(exc, BudgetExceeded) else "provider_output_invalid"
            result.checkpoints.append({"node_id": parent_id, "status": "blocked",
                                       "reason": result.stopped_reason, "message": str(exc)})
            break
        result.feedback.extend({"target_node_id": parent_id, "proposal": text, "status": "PROPOSED",
                                "applied": False} for text in proposal.feedback)
        if proposal.information_gain < min_information_gain:
            result.checkpoints.append({"node_id": parent_id, "status": "stopped",
                                       "reason": "information_gain_threshold",
                                       "information_gain": proposal.information_gain,
                                       "information_gain_method": "provider-declared heuristic"})
            continue
        proposed_children: list[Node] = []
        invalid = None
        for index, child in enumerate(proposal.children[:request["max_children"]], 1):
            attributes = {constraint.key: constraint.expected for constraint in constraints
                          if constraint.scope == "design"}
            attributes.update(child.attributes)
            for constraint in constraints:
                if constraint.scope == "design" and attributes.get(constraint.key) != constraint.expected:
                    invalid = f"Design constraint violated: {constraint.id}"
                if (constraint.scope == "invariant" and child.transition is not None and
                        constraint.key in child.transition.effects and
                        child.transition.effects[constraint.key] != constraint.expected):
                    invalid = f"Proposed effect violates invariant: {constraint.id}"
            identifier = f"{parent_id}.r{index}"
            suffix = 1
            while identifier in result.graph.nodes or any(item.id == identifier for item in proposed_children):
                suffix += 1
                identifier = f"{parent_id}.r{index}.{suffix}"
            attributes.update({"parent_purpose": parent.purpose,
                               "refinement_uncertainty": proposal.uncertainty,
                               "refinement_method": provider.name})
            proposed_children.append(Node(
                id=identifier, kind=child.kind, label=child.label, level=parent.level + 1,
                parent_id=parent_id, status=CanonStatus.PROPOSED, time=parent.time,
                order=parent.order + index / 100, revelation_order=parent.revelation_order + index / 100,
                threads=list(parent.threads), attributes=attributes, transition=child.transition,
                hard_constraints=constraints, soft_constraints=list(parent.soft_constraints),
                evidence=list(parent.evidence), purpose=child.purpose,
                duration=parent.duration / len(proposal.children), confidence=0.25,
                completion="requires_review", provenance=Provenance(
                    author="provider", method="proposed_decomposition", model=provider.name,
                    operation="refine")))
        candidate = result.graph.clone()
        if invalid is None:
            for child in proposed_children:
                candidate.add_node(child)
                edge_id = f"refinement:{child.id}:{parent_id}"
                while edge_id in candidate.edges:
                    edge_id += ":new"
                candidate.add_edge(Edge(id=edge_id, source=child.id, target=parent_id,
                                        kind=EdgeType.BELONGS_TO, status=CanonStatus.PROPOSED,
                                        provenance=child.provenance))
            failures = [finding for finding in candidate.validate() if finding.severity == "error"]
            if failures:
                invalid = failures[0].message
        if invalid is not None:
            result.stopped_reason = "validation_rejected"
            result.checkpoints.append({"node_id": parent_id, "status": "rejected", "reason": invalid})
            result.feedback.append({"target_node_id": parent_id, "proposal": invalid,
                                    "status": "PROPOSED", "applied": False})
            continue
        result.graph = candidate
        child_ids = [child.id for child in proposed_children]
        result.children.extend(child_ids)
        result.checkpoints.append({"node_id": parent_id, "status": "proposed", "children": child_ids,
                                   "inherited_constraints": [item.id for item in constraints],
                                   "information_gain": proposal.information_gain,
                                   "information_gain_method": "provider-declared heuristic",
                                   "validation": "schema, hierarchy, inherited design constraints and explicit invariant effects",
                                   "unverified": "Canonical simulation and artistic quality require review",
                                   "truncated_siblings": len(proposal.children) > len(child_ids)})
        frontier.extend((identifier, relative_depth + 1) for identifier in child_ids)
    result.telemetry.retrieved_graph_nodes = len(retrieved_ids)
    result.telemetry.affected_narrative_nodes = list(result.children)
    result.telemetry.latency_seconds = time.perf_counter() - started
    return result
