"""Atomic chronological simulation; observations and belief never imply knowledge."""

from pydantic import Field

from .graph import StoryGraph
from .schema import CanonStatus, Finding, Record, State


class SimulationResult(Record):
    state: State
    findings: list[Finding] = Field(default_factory=list)
    applied: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)


def simulate(graph: StoryGraph) -> SimulationResult:
    document = graph.document
    result = SimulationResult(state=document.initial_state)
    constraints = [c for c in document.constraints if c.scope == "invariant"]

    def invariant_findings(state, node_ids):
        return [Finding(code="INVARIANT", message=c.description or c.id, node_ids=node_ids, evidence=[c.id])
                for c in constraints if c.key not in state.values or state.values[c.key] != c.expected]

    result.findings.extend(graph.validate())
    result.findings.extend(invariant_findings(result.state, []))
    if any(f.severity == "error" for f in result.findings):
        return result
    events = sorted((n for n in document.nodes if n.transition and n.status == CanonStatus.CANON),
                    key=lambda n: (n.time, n.id))
    for node in events:
        transition = node.transition
        before = result.state.model_copy(deep=True)
        failures = []
        for key, expected in transition.requires.items():
            if key not in before.values or before.values[key] != expected:
                failures.append(Finding(code="PRECONDITION", message=f"{key} must equal {expected!r}; observed {before.values.get(key)!r}", node_ids=[node.id], evidence=[key]))
        for actor, facts in transition.requires_knowledge.items():
            for fact in facts:
                if fact not in before.knowledge.get(actor, []):
                    failures.append(Finding(code="UNKNOWN_SECRET", message=f"{actor} cannot act on unknown fact {fact}", node_ids=[node.id], evidence=[actor, fact]))
        for key, value in transition.effects.items():
            if key in before.irreversible and value != before.values.get(key):
                # An exception is an established CANON Rule, not an arbitrary label.
                exceptions = [graph.get(rule_id) for rule_id in transition.exceptions if rule_id in graph.nodes]
                valid_exception = any(r.kind == "Rule" and r.status == CanonStatus.CANON and r.time <= node.time and r.attributes.get("exception_for") == key for r in exceptions)
                if not valid_exception:
                    failures.append(Finding(code="IRREVERSIBLE", message=f"Cannot reverse {key} without an established exception", node_ids=[node.id], evidence=[key]))
        after = before.model_copy(deep=True)
        after.values.update(transition.effects)
        for actor, facts in transition.knowledge_updates.items():
            after.knowledge[actor] = sorted(set(after.knowledge.get(actor, [])) | set(facts))
        for actor, beliefs in transition.belief_updates.items():
            after.beliefs[actor] = list(beliefs)
        for key in transition.irreversible:
            if key not in after.values:
                failures.append(Finding(code="MISSING_IRREVERSIBLE_VALUE", message=f"No value to lock for {key}", node_ids=[node.id]))
        after.irreversible = sorted(set(after.irreversible) | set(transition.irreversible))
        failures.extend(invariant_findings(after, [node.id]))
        for constraint in graph.constraints_for(node.id):
            if constraint in constraints:
                continue
            if constraint.scope == "invariant" and (constraint.key not in after.values or after.values[constraint.key] != constraint.expected):
                failures.append(Finding(code="LOCAL_INVARIANT", message=constraint.description or constraint.id, node_ids=[node.id], evidence=[constraint.id]))
        result.findings.extend(failures)
        result.trace.append({"node_id": node.id, "time": node.time, "presentation_order": node.order,
                             "revelation_order": node.revelation_order, "applied": not failures,
                             "before": before.model_dump(mode="json"),
                             "after": (before if failures else after).model_dump(mode="json")})
        if not failures:
            result.state = after
            result.applied.append(node.id)
    return result
