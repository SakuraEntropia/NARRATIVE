"""Bounded, evidence-bearing counterfactual revision; no differentiable art score.

Candidate text comes from explicitly authored ``repair_candidates`` annotations.
The offline implementation does not impersonate an autonomous creative model.
"""

from __future__ import annotations

import copy
import time
from collections import deque
from typing import Any

from pydantic import Field

from narrative.core.graph import GraphError, StoryGraph
from narrative.core.schema import CanonStatus, Provenance, Record
from narrative.core.state_machine import simulate

DEPENDENCY_TYPES = {"CAUSES", "REQUIRES", "ENABLES", "MOTIVATES", "CONSTRAINS", "REVEALS", "KNOWS", "TRANSFORMS"}
ASSOCIATIVE_TYPES = {"SYMBOLIZES", "PARALLELS", "CONTRASTS", "CONTRADICTS", "FORESHADOWS", "PAYS_OFF"}


class Pivot(Record):
    id: str
    target: str
    node_id: str
    changes: dict[str, Any]
    kind: str = "authored_revision"
    evidence: list[str] = Field(default_factory=list)
    cost: float = Field(default=1, ge=0)
    confidence: float = Field(default=0.6, ge=0, le=1)
    status: CanonStatus = CanonStatus.PROPOSED
    method: str = "deterministic_authored_candidate"
    version: int = Field(default=1, ge=1)
    provenance: Provenance = Field(default_factory=lambda: Provenance(
        author="authored candidate annotation", method="deterministic_authored_candidate"))


def _active(edge) -> bool:
    return edge.status == CanonStatus.CANON


def _evidence_refs(edge) -> list[str]:
    return [item.node_id or item.source for item in edge.evidence]


def _transition_dependencies(graph: StoryGraph) -> dict[str, list[dict]]:
    """Project explicit transition ledgers without creating canonical edges.

    Earlier writers are possible providers, not guarantees of event success;
    chronological simulation remains the authority for actual state.
    """
    effects, knowledge = {}, {}
    result = {}
    transitions = sorted((node for node in graph.nodes.values()
                          if node.transition and node.status == CanonStatus.CANON),
                         key=lambda node: (node.time, node.id))
    for node in transitions:
        incoming = []
        for key in node.transition.requires:
            for source in effects.get(key, []):
                incoming.append({"source": source, "target": node.id, "kind": "STATE_PRECONDITION",
                                 "evidence": [source, node.id], "key": key,
                                 "edge_id": f"state:{source}:{node.id}:{key}"})
        for actor, facts in node.transition.requires_knowledge.items():
            for fact in facts:
                for source in knowledge.get((actor, fact), []):
                    incoming.append({"source": source, "target": node.id, "kind": "KNOWLEDGE_PRECONDITION",
                                     "evidence": [source, node.id], "key": f"{actor}:{fact}",
                                     "edge_id": f"knowledge:{source}:{node.id}:{actor}:{fact}"})
        result[node.id] = incoming
        for key in node.transition.effects:
            effects.setdefault(key, []).append(node.id)
        for actor, facts in node.transition.knowledge_updates.items():
            for fact in facts:
                knowledge.setdefault((actor, fact), []).append(node.id)
    return result


def backward_influence(graph: StoryGraph, target: str, max_depth: int = 8) -> dict:
    """Trace evidence-bearing dependencies, retaining associations separately.

    Rankings describe graph proximity, edge weight and recorded confidence. They
    are candidate intervention priorities, not proof of narrative root cause.
    """
    graph.get(target)
    if max_depth < 0 or max_depth > 100:
        raise ValueError("max_depth must lie between 0 and 100")
    queue = deque([(target, 0, [])])
    visited = {target}
    causes: dict[str, dict] = {}
    associations = []
    unsupported = []
    traversed_edges = []
    ledger_dependencies = _transition_dependencies(graph)
    derived_records = []
    while queue:
        current, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in sorted(graph.incoming(current), key=lambda e: e.id):
            if not _active(edge):
                continue
            kind = str(edge.kind)
            record = {"edge_id": edge.id, "source": edge.source, "target": edge.target,
                      "kind": kind, "evidence": _evidence_refs(edge)}
            if kind in ASSOCIATIVE_TYPES:
                associations.append(record)
                continue
            if kind not in DEPENDENCY_TYPES:
                continue
            if not edge.evidence:
                unsupported.append(record)
                continue
            distance = depth + 1
            new_path = path + [edge.id]
            priority = edge.weight * edge.confidence / distance
            if edge.source != target and (edge.source not in causes or priority > causes[edge.source]["priority"]):
                causes[edge.source] = {"node_id": edge.source, "distance": distance,
                                       "priority": priority, "path": new_path,
                                       "evidence": _evidence_refs(edge), "relation": kind,
                                       "locked": graph.get(edge.source).locked}
            traversed_edges.append(edge.id)
            if edge.source not in visited:
                visited.add(edge.source)
                queue.append((edge.source, distance, new_path))
        for record in ledger_dependencies.get(current, []):
            distance = depth + 1
            source = record["source"]
            priority = min(graph.get(source).confidence, graph.get(current).confidence) / distance
            new_path = path + [record["edge_id"]]
            if source not in causes or priority > causes[source]["priority"]:
                causes[source] = {"node_id": source, "distance": distance,
                                  "priority": priority, "path": new_path,
                                  "evidence": record["evidence"], "relation": record["kind"],
                                  "locked": graph.get(source).locked,
                                  "method": "explicit transition prerequisite projection"}
            derived_records.append(record)
            if source not in visited:
                visited.add(source)
                queue.append((source, distance, new_path))
    return {"target": target, "candidate_root_causes": sorted(causes.values(), key=lambda x: (-x["priority"], x["node_id"])),
            "dependency_edges": sorted(set(traversed_edges)), "associations": associations,
            "transition_dependencies": derived_records,
            "unsupported_dependencies": unsupported, "max_depth": max_depth,
            "method": "bounded evidence-bearing graph traversal",
            "limitations": ["A typed edge records an authored claim, not empirically established causation.",
                            "Symbolic and foreshadowing relationships are retained without treating them as causal proof."]}


def affected_nodes(graph: StoryGraph, changed: list[str]) -> list[str]:
    """Compute dependency closure, including later transition state/knowledge use."""
    nodes = graph.nodes
    for node_id in changed:
        graph.get(node_id)
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in graph.edges.values():
        if _active(edge) and str(edge.kind) in DEPENDENCY_TYPES:
            dependencies[edge.source].add(edge.target)
    for target, records in _transition_dependencies(graph).items():
        for record in records:
            dependencies[record["source"]].add(target)
    result = set(changed)
    queue = deque(changed)
    while queue:
        for dependent in dependencies[queue.popleft()]:
            if dependent not in result:
                result.add(dependent)
                queue.append(dependent)
    return sorted(result)


def propose_pivots(graph: StoryGraph, target: str, max_candidates: int = 3, max_depth: int = 8) -> list[Pivot]:
    """Select authored candidate repairs with present evidence and bounded count."""
    if not 0 <= max_candidates <= 100:
        raise ValueError("max_candidates must lie between 0 and 100")
    influence = backward_influence(graph, target, max_depth=max_depth)
    sources = [target] + [item["node_id"] for item in influence["candidate_root_causes"]]
    candidates = []
    seen = set()
    for source in sources:
        for annotation in graph.get(source).attributes.get("repair_candidates", []):
            if not isinstance(annotation, dict):
                raise ValueError(f"Malformed authored candidate at {source}")
            payload = {**annotation, "target": target}
            payload.setdefault("node_id", source)
            candidate = Pivot.model_validate(payload)
            if candidate.id in seen:
                continue
            graph.get(candidate.node_id)
            if not candidate.evidence or any(item not in graph.nodes for item in candidate.evidence):
                raise ValueError(f"Candidate {candidate.id} must reference present graph evidence")
            if candidate.status != CanonStatus.PROPOSED:
                raise ValueError("Authored repair candidates must remain PROPOSED")
            seen.add(candidate.id)
            candidates.append(candidate)
    return sorted(candidates, key=lambda p: (p.cost, -p.confidence, p.id))[:max_candidates]


def _apply(branch: StoryGraph, pivot: Pivot, approve: bool, authorized_locked: set[str]) -> None:
    current = branch.get(pivot.node_id)
    if current.locked and pivot.node_id not in authorized_locked:
        raise GraphError(f"Locked canon requires explicit authorization: {pivot.node_id}")
    payload = current.model_dump(mode="json")
    allowed = {"attributes", "transition", "label", "purpose", "time", "order", "revelation_order", "duration", "threads"}
    for path, value in pivot.changes.items():
        fields = path.split(".")
        if fields[0] not in allowed or (len(fields) > 1 and fields[0] not in {"attributes", "transition"}):
            raise ValueError(f"Unsupported revision field: {path}")
        destination = payload
        for field in fields[:-1]:
            if field not in destination or destination[field] is None:
                destination[field] = {}
            if not isinstance(destination[field], dict):
                raise ValueError(f"Revision path is not a mapping: {path}")
            destination = destination[field]
        destination[fields[-1]] = copy.deepcopy(value)
    payload["status"] = CanonStatus.CANON if approve else CanonStatus.PROPOSED
    payload["provenance"] = pivot.provenance.model_copy(update={"operation": pivot.id}).model_dump()
    payload["confidence"] = pivot.confidence
    branch.update_node(pivot.node_id, payload, authorized=approve or pivot.node_id in authorized_locked)


def _weak_decisions(graph: StoryGraph) -> list[str]:
    return [node.id for node in graph.nodes.values()
            if node.kind == "Decision" and not node.attributes.get("motivation")
            and not any(e.kind == "MOTIVATES" and e.evidence and _active(e) for e in graph.incoming(node.id))]


def _finding_key(finding) -> tuple:
    return finding.code, tuple(finding.node_ids), tuple(finding.evidence)


def _analysis(graph: StoryGraph) -> tuple[dict, dict]:
    from narrative.evaluation.adversarial import review
    from narrative.evaluation.benchmarks import evaluate

    return evaluate(graph), review(graph)


def evaluate_pivot(graph: StoryGraph, pivot: Pivot | dict, *, approve: bool = False,
                   authorized_locked: list[str] | tuple[str, ...] = ()) -> dict:
    """Evaluate a private branch and return ``{branch, report}``.

    Without explicit approval, the returned edited node is PROPOSED. A second,
    ephemeral copy treats it as canon solely to measure the counterfactual. This
    validation never commits or promotes the original or proposed branch.
    """
    start = time.perf_counter()
    pivot = Pivot.model_validate(pivot) if isinstance(pivot, dict) else pivot.model_copy(deep=True)
    graph.get(pivot.target)
    if not pivot.evidence or any(item not in graph.nodes for item in pivot.evidence):
        raise ValueError("Pivot requires evidence references to existing nodes")
    branch = graph.clone()
    _apply(branch, pivot, approve, set(authorized_locked))
    counterfactual = branch.clone()
    if not approve:
        current = counterfactual.get(pivot.node_id)
        counterfactual.update_node(pivot.node_id, {"status": CanonStatus.CANON}, authorized=True)
        assert current.status == CanonStatus.PROPOSED
    before = simulate(graph)
    after = simulate(counterfactual)
    before_errors = [f for f in before.findings if f.severity == "error"]
    after_errors = [f for f in after.findings if f.severity == "error"]
    before_keys = {_finding_key(f) for f in before_errors}
    new_errors = [f for f in after_errors if _finding_key(f) not in before_keys]
    weak_before, weak_after = _weak_decisions(graph), _weak_decisions(counterfactual)
    benchmark, critiques = _analysis(counterfactual)
    closure = affected_nodes(graph, [pivot.node_id])
    influence = backward_influence(graph, pivot.target)
    defect = {"code": "WEAK_MOTIVATION" if pivot.target in weak_before else "AUTHOR_SELECTED_TARGET",
              "node_id": pivot.target, "evidence": [pivot.target],
              "description": "No stated motive or evidenced incoming motivation relation" if pivot.target in weak_before else "Revision target selected by the author; no artistic defect is inferred",
              "method": "structural proxy"}
    report = {
        "defect": defect, "candidate_root_causes": influence["candidate_root_causes"],
        "pivot": pivot.model_dump(mode="json"), "affected_nodes": closure,
        "expected_improvement": {"structural_errors_removed": len(before_errors) - len(after_errors),
                                 "unsupported_decisions_removed": len(weak_before) - len(weak_after),
                                 "method": "observed differences on the explicit counterfactual", "artistic_improvement": None},
        "regression_risks": [f.model_dump(mode="json") for f in new_errors],
        "risk_notes": ["A supplied motivation annotation does not prove that a reader finds the decision convincing.",
                       "Dependency closure can omit unrepresented semantic dependencies; a full simulation was also run."],
        "confidence": pivot.confidence, "revision_cost": pivot.cost,
        "estimated_model_cost": {"api_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usd": 0,
                                 "method": "No model invocation; authored candidate and deterministic audits"},
        "simulation": after.model_dump(mode="json"), "benchmark": benchmark, "critiques": critiques,
        "objectives": {"hard_errors": len(after_errors), "unsupported_decisions": len(weak_after), "revision_cost": pivot.cost},
        "valid": not after_errors, "canonical_approval": approve,
        "validation_scope": "approved isolated branch" if approve else "ephemeral counterfactual only; returned edit remains PROPOSED",
        "latency_seconds": time.perf_counter() - start,
    }
    return {"branch": branch, "report": report}


def pareto_select(reports: list[dict]) -> list[str]:
    """Return nondominated valid pivot IDs; hard validity always takes priority."""
    eligible = [r for r in reports if r.get("valid")]
    frontier = []
    for candidate in eligible:
        values = candidate["objectives"]
        dominated = any(
            other is not candidate
            and all(other["objectives"][key] <= value for key, value in values.items())
            and any(other["objectives"][key] < value for key, value in values.items())
            for other in eligible
        )
        if not dominated:
            frontier.append(candidate["pivot"]["id"])
    return frontier


def duel(graph: StoryGraph, pivots: list[Pivot] | None = None, *, target: str | None = None,
         max_candidates: int = 3, max_iterations: int = 1) -> dict:
    """Compare a finite authored candidate pool without autonomous acceptance."""
    if not 1 <= max_iterations <= 100 or not 1 <= max_candidates <= 100:
        raise ValueError("Candidate and iteration limits must lie between 1 and 100")
    if pivots is None:
        if target is None:
            raise ValueError("A target or explicit pivot list is required")
        pivots = propose_pivots(graph, target, max_candidates=max_candidates)
    reports = []
    for pivot in pivots[:min(max_candidates, max_iterations * max_candidates)]:
        try:
            reports.append(evaluate_pivot(graph, pivot)["report"])
        except (GraphError, ValueError) as error:
            reports.append({"pivot": pivot.model_dump(mode="json"), "valid": False,
                            "error": str(error), "objectives": {"hard_errors": 1, "unsupported_decisions": 0, "revision_cost": pivot.cost}})
    return {"candidates": reports, "pareto_set": pareto_select(reports), "iterations": 1 if reports else 0,
            "stop_reason": "finite authored candidate pool exhausted" if len(pivots) <= max_candidates else "candidate budget exhausted",
            "max_iterations": max_iterations, "max_candidates": max_candidates,
            "acceptance": "No branch accepted; explicit author approval required",
            "limitations": ["Offline candidates and critics are deterministic and not independent model readers.",
                            "Pareto objectives are structural proxies and revision cost, not artistic quality."]}
