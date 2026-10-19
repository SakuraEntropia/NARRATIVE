"""Bounded graph context and dependency-aware, explicitly invalidated caches.

Context units are UTF-8 bytes, a conservative estimate rather than billed model
tokens. A returned overflow must be resolved before submitting context to a model.
"""

from __future__ import annotations

import copy
import json
import math
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def estimate_units(value: Any) -> int:
    """Conservative byte-unit context estimate; never a tokenizer measurement."""
    return len(json.dumps(_plain(value), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))


class BudgetExceeded(ValueError):
    """A finite operation, iteration or project budget would be exceeded."""


@dataclass
class Budget:
    """Composable budgets: operation.parent=iteration; iteration.parent=project.

    Reservations are checked across all scopes before any counter is changed.
    Unknown API cost cannot satisfy a hard monetary budget.
    """

    max_context_units: int = 120_000
    max_output_units: int = 120_000
    max_calls: int = 16
    max_cost_usd: float | None = None
    scope: str = "operation"
    parent: Budget | None = field(default=None, repr=False)
    context_units: int = 0
    output_units: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if min(self.max_context_units, self.max_output_units, self.max_calls) < 0:
            raise ValueError("Budget limits must be nonnegative")
        if self.max_cost_usd is not None and (not math.isfinite(self.max_cost_usd) or self.max_cost_usd < 0):
            raise ValueError("Cost limit must be nonnegative")

    def reserve(self, *, context_units: int = 0, output_units: int = 0,
                calls: int = 0, cost_usd: float | None = 0.0) -> None:
        if min(context_units, output_units, calls) < 0 or (cost_usd is not None and
                                                       (not math.isfinite(cost_usd) or cost_usd < 0)):
            raise ValueError("Budget reservations must be nonnegative")
        chain: list[Budget] = []
        current: Budget | None = self
        while current is not None:
            if any(current is item for item in chain):
                raise ValueError("Budget parent cycle")
            chain.append(current)
            current = current.parent
        for item in chain:
            checks = ((item.context_units + context_units, item.max_context_units, "context"),
                      (item.output_units + output_units, item.max_output_units, "output"),
                      (item.calls + calls, item.max_calls, "calls"))
            for value, limit, name in checks:
                if value > limit:
                    raise BudgetExceeded(f"{item.scope} {name} budget exceeded: {value} > {limit}")
            if item.max_cost_usd is not None:
                if cost_usd is None:
                    raise BudgetExceeded(f"{item.scope} API cost is unknown under a hard cost limit")
                if item.cost_usd + cost_usd > item.max_cost_usd:
                    raise BudgetExceeded(f"{item.scope} cost budget exceeded")
        for item in chain:
            item.context_units += context_units
            item.output_units += output_units
            item.calls += calls
            item.cost_usd += cost_usd or 0.0


@dataclass
class Telemetry:
    provider: str = "deterministic"
    prompt_tokens: int | None = 0
    completion_tokens: int | None = 0
    estimated_context_units: int = 0
    estimated_output_units: int = 0
    estimate_method: str = "UTF-8 JSON bytes; conservative context estimate, not billed tokens"
    cache_hits: int = 0
    retrieved_graph_nodes: int = 0
    estimated_api_cost_usd: float | None = 0.0
    latency_seconds: float = 0.0
    evaluation_iteration: int = 0
    affected_narrative_nodes: list[str] = field(default_factory=list)
    calls: int = 0
    retries: int = 0

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContextResult:
    node_ids: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    hard_constraints: list[dict[str, Any]]
    state: dict[str, Any]
    estimated_tokens: int
    overflow: bool
    omitted_ids: list[str]
    telemetry: Telemetry
    warnings: list[str] = field(default_factory=list)

    def model_dump(self, **_: Any) -> dict[str, Any]:
        result = asdict(self)
        result["estimated_tokens_method"] = self.telemetry.estimate_method
        return result


def _kind(record: Any) -> str:
    kind = getattr(record, "kind", "")
    return str(getattr(kind, "value", kind)).lower()


def _is_causal(edge: Any) -> bool:
    return any(word in _kind(edge) for word in
               ("caus", "depend", "enabl", "require", "precondition", "consequence",
                "motivat", "transform", "reveal"))


def _is_long_range(edge: Any) -> bool:
    return any(word in _kind(edge) for word in ("foreshadow", "payoff", "pays_off", "setup"))


def retrieve(graph: Any, targets: list[str] | str, token_budget: int = 12_000,
             *, max_nodes: int = 64, max_hops: int = 8) -> ContextResult:
    """Retrieve bounded evidence, keeping global/ancestor hard constraints.

    Direct targets, causal predecessors, explicitly referenced rules/characters,
    and setup/payoff endpoints are mandatory evidence. If they cannot fit, the
    result is explicitly unusable (overflow=True); it never silently drops them.
    Summaries can be included as nodes, but never replace original evidence.
    """
    started = time.perf_counter()
    if token_budget < 0 or max_nodes < 1 or max_hops < 0:
        raise ValueError("Invalid context budget or traversal bound")
    targets = [targets] if isinstance(targets, str) else list(dict.fromkeys(targets))
    nodes, edges, document = graph.nodes, graph.edges, graph.document
    for identifier in targets:
        if identifier not in nodes:
            raise KeyError(f"Unknown target node: {identifier}")
    incoming: dict[str, list[Any]] = {identifier: [] for identifier in nodes}
    outgoing: dict[str, list[Any]] = {identifier: [] for identifier in nodes}
    for edge in edges.values():
        incoming.setdefault(edge.target, []).append(edge)
        outgoing.setdefault(edge.source, []).append(edge)

    constraints = [{"source": "project", "source_status": "CANON", "constraint": _plain(item)}
                   for item in document.constraints]
    ancestors: set[str] = set()
    constrained_sources: set[str] = set()

    def preserve_ancestor_constraints(identifier: str) -> None:
        current = nodes[identifier]
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            ancestors.add(current.id)
            if current.id not in constrained_sources:
                constrained_sources.add(current.id)
                for constraint in current.hard_constraints:
                    constraints.append({"source": current.id, "source_status": str(current.status),
                                        "constraint": _plain(constraint)})
            current = nodes.get(current.parent_id)

    for identifier in targets:
        preserve_ancestor_constraints(identifier)

    mandatory: set[str] = set(targets)
    candidates: dict[str, int] = {identifier: 100 for identifier in targets}
    queue = deque((identifier, 0) for identifier in targets)
    expanded: set[str] = set()
    truncated = False
    while queue:
        identifier, hops = queue.popleft()
        if identifier in expanded:
            continue
        if len(expanded) >= max_nodes:
            truncated = True
            break
        expanded.add(identifier)
        node = nodes[identifier]
        refs: set[str] = set()
        for key in ("world_rules", "rules", "required_rules", "characters", "character_ids",
                    "character_id", "evidence_nodes", "knowledge_nodes", "source_nodes", "summary_of"):
            values = node.attributes.get(key, [])
            refs.update([values] if isinstance(values, str) else
                        [value for value in values if isinstance(value, str)]
                        if isinstance(values, (list, tuple)) else [])
        if node.transition is not None:
            refs.update(node.transition.participants)
        refs.update(item.node_id for item in node.evidence if item.node_id is not None)
        related = incoming.get(identifier, []) + outgoing.get(identifier, [])
        for edge in related:
            other = edge.source if edge.target == identifier else edge.target
            is_required = (_is_causal(edge) and edge.target == identifier) or _is_long_range(edge)
            is_required |= any(word in _kind(edge) for word in
                               ("knowledge", "character", "rule", "knows", "believes", "observes", "constrain"))
            if is_required:
                refs.add(other)
            else:
                candidates[other] = max(candidates.get(other, 0), 20)
        for other in sorted(refs):
            if other not in nodes:
                continue
            mandatory.add(other)
            candidates[other] = max(candidates.get(other, 0), 90 - hops)
            if other not in expanded:
                if hops < max_hops:
                    queue.append((other, hops + 1))
                else:
                    truncated = True
    # Rules are explicit evidence; a rule declared globally cannot disappear due
    # to low semantic similarity. Explicit references handle local rules above.
    for identifier, node in nodes.items():
        if "rule" in _kind(node) and node.attributes.get("global", False):
            mandatory.add(identifier)
            candidates[identifier] = 95
    for identifier in sorted(mandatory):
        preserve_ancestor_constraints(identifier)
    for identifier in ancestors:
        candidates[identifier] = max(candidates.get(identifier, 0), 70)

    def payload(selected: set[str]) -> dict[str, Any]:
        selected_nodes = [nodes[item] for item in sorted(selected)]
        required_keys: set[str] = set()
        people: set[str] = set()
        for node in selected_nodes:
            if node.transition is not None:
                required_keys.update(node.transition.requires)
                required_keys.update(node.transition.effects)
                required_keys.update(node.transition.resources)
                people.update(node.transition.participants)
                people.update(node.transition.requires_knowledge)
                people.update(node.transition.knowledge_updates)
                people.update(node.transition.belief_updates)
        initial = document.initial_state
        state = {"values": {key: value for key, value in initial.values.items() if key in required_keys},
                 "knowledge": {key: value for key, value in initial.knowledge.items() if key in people},
                 "beliefs": {key: value for key, value in initial.beliefs.items() if key in people},
                 "irreversible": list(initial.irreversible)}
        return {"nodes": [_plain(node) for node in selected_nodes],
                "edges": [_plain(edge) for edge in edges.values()
                          if edge.source in selected and edge.target in selected],
                "hard_constraints": constraints, "state": state}

    selected = set(targets[:max_nodes])
    for identifier in sorted(mandatory - selected):
        if len(selected) >= max_nodes:
            break
        selected.add(identifier)
    contents = payload(selected)
    overflow = truncated or len(mandatory) > max_nodes or estimate_units(contents) > token_budget
    if not overflow:
        for identifier in sorted(candidates, key=lambda item: (-candidates[item], item)):
            if identifier in selected or len(selected) >= max_nodes:
                continue
            proposed = selected | {identifier}
            new_contents = payload(proposed)
            if estimate_units(new_contents) <= token_budget:
                selected, contents = proposed, new_contents
    estimated = estimate_units(contents)
    warnings = []
    if truncated:
        warnings.append("Required dependency expansion reached its traversal bound; context is incomplete")
    if overflow:
        warnings.append("Mandatory evidence/constraints exceed context limits; do not submit this partial context")
    telemetry = Telemetry(estimated_context_units=estimated, retrieved_graph_nodes=len(selected),
                          affected_narrative_nodes=sorted(selected),
                          latency_seconds=time.perf_counter() - started)
    return ContextResult(sorted(selected), contents["nodes"], contents["edges"], constraints,
                         contents["state"], estimated, overflow,
                         sorted(set(nodes) - selected), telemetry, warnings)


class DependencyCache:
    """Local in-memory results whose dependencies must be declared explicitly.

    All directed dependency relations and parent summaries are invalidated.
    Periodic full_audit=True deliberately clears every entry to catch undeclared
    dependencies; local invalidation cannot prove those dependencies absent.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[Any, set[str]]] = {}
        self.hits = 0

    def set(self, key: str, value: Any, dependencies: list[str] | set[str]) -> None:
        self._entries[key] = (copy.deepcopy(value), set(dependencies))

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._entries:
            return default
        self.hits += 1
        return copy.deepcopy(self._entries[key][0])

    def invalidate(self, changed_ids: list[str] | set[str], graph: Any,
                   *, full_audit: bool = False) -> list[str]:
        if full_audit:
            removed = sorted(self._entries)
            self._entries.clear()
            return removed
        nodes, edges = graph.nodes, graph.edges
        affected = set(changed_ids)
        adjacency: dict[str, set[str]] = {}
        for edge in edges.values():
            hierarchy_edge = (_kind(edge) == "belongs_to" and edge.source in nodes and
                              nodes[edge.source].parent_id == edge.target)
            if not hierarchy_edge:
                adjacency.setdefault(edge.source, set()).add(edge.target)
            if edge.id in affected:
                affected.update((edge.source, edge.target))
        for node in nodes.values():
            if node.parent_id:
                adjacency.setdefault(node.parent_id, set()).add(node.id)
        queue = deque(affected)
        while queue:
            for target in adjacency.get(queue.popleft(), set()):
                if target not in affected:
                    affected.add(target)
                    queue.append(target)
        # Ancestor summaries depend on a changed descendant. Their invalidation
        # must not fan back down into unrelated siblings through the root.
        for identifier in list(affected):
            current = nodes.get(identifier)
            seen: set[str] = set()
            while current is not None and current.parent_id and current.id not in seen:
                seen.add(current.id)
                affected.add(current.parent_id)
                current = nodes.get(current.parent_id)
        removed = sorted(key for key, (_, dependencies) in self._entries.items()
                         if dependencies & affected)
        for key in removed:
            del self._entries[key]
        return removed
