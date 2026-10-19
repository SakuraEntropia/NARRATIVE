"""Separate declared author, character and audience information ledgers."""

from .attention import canonical, token


def _facts(value, node_id=None):
    if value is None or value is False:
        return []
    if value is True and node_id is not None:
        return [node_id]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(fact, str) for fact in value):
        return value
    raise ValueError("audience knowledge must be a fact ID, list of fact IDs, or a node audience_knows boolean")


def analyze_information(graph, simulation=None):
    nodes, edges = canonical(graph)
    from narrative.core.state_machine import simulate
    simulation = simulation if simulation is not None else simulate(graph)
    state = graph.document.initial_state
    knowledge = {person: set(facts) for person, facts in state.knowledge.items()}
    audience = set(_facts(graph.document.metadata.get("audience_initial_knowledge", [])))
    author = sorted(node.id for node in nodes.values() if token(node.kind) in {"FACT", "RULE", "WORLDSTATE"})
    trace = []
    unearned = []
    reveal_edges = {}
    for edge in edges:
        if token(edge.kind) == "REVEALS":
            reveal_edges.setdefault(edge.source, []).append((edge.target, edge.id))
    applied_trace = {entry["node_id"]: entry for entry in simulation.trace}
    for finding in simulation.findings:
        if finding.code == "UNKNOWN_SECRET" and len(finding.evidence) >= 2:
            unearned.append({"node_id": finding.node_ids[0], "character": finding.evidence[0], "missing": [finding.evidence[1]], "evidence": [*finding.node_ids, *finding.evidence]})
    for node in sorted(nodes.values(), key=lambda node: (node.time, node.id)):
        entry = applied_trace.get(node.id)
        if entry:
            knowledge = {person: set(facts) for person, facts in entry["after"]["knowledge"].items()}
        trace.append({"node_id": node.id, "diegetic_time": node.time, "transition_applied": entry["applied"] if entry else None, "characters": {person: sorted(facts) for person, facts in sorted(knowledge.items())}, "evidence": [node.id]})
    audience_trace = []
    unexecuted_revelations = []
    for node in sorted(nodes.values(), key=lambda node: (node.revelation_order, node.order, node.id)):
        declared = _facts(node.attributes.get("audience_knows", []), node.id)
        audience.update(declared)
        failed = bool(node.transition and not applied_trace.get(node.id, {}).get("applied", False))
        declared_reveals = reveal_edges.get(node.id, [])
        if failed:
            unexecuted_revelations.extend({"node_id": node.id, "fact_id": target, "edge_id": edge_id} for target, edge_id in declared_reveals)
        else:
            audience.update(target for target, _ in declared_reveals)
        audience_trace.append({"node_id": node.id, "revelation_order": node.revelation_order, "known": sorted(audience), "explicitly_declared": declared, "unexecuted_revelation_edges": [edge_id for _, edge_id in declared_reveals] if failed else [], "evidence": [node.id, *[edge_id for _, edge_id in declared_reveals]]})
    return {"author_facts": author, "character_timeline": trace, "audience_timeline": audience_trace, "unearned_knowledge": unearned, "unexecuted_revelations": unexecuted_revelations, "simulation_findings": [finding.model_dump(mode="json") for finding in simulation.findings], "method": "simulated_character_ledger_and_declared_audience_ledger", "limitations": ["Character knowledge changes only after successfully simulated transitions; a globally invalid graph may prevent all simulation.", "Audience state follows revelation_order. Explicit audience_knows annotations declare presented information; REVEALS from failed executable events are flagged and withheld.", "Silence plausibility and fair withholding require reader judgment; no unsupported motive is inferred."]}
