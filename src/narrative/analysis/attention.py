"""Sparse, typed graph attention. This is not Transformer attention or art scoring."""

from collections import Counter, defaultdict
from math import ceil


RELATIONS = {
    "causal": {"CAUSES", "REQUIRES", "ENABLES", "CONSTRAINS"},
    "character": {"MOTIVATES", "TRANSFORMS", "BELONGS_TO"},
    "thematic": {"SYMBOLIZES", "PARALLELS", "CONTRASTS", "CONTRADICTS"},
    "foreshadowing": {"FORESHADOWS", "PAYS_OFF"},
    "emotional": {"MOTIVATES", "TRANSFORMS"},
    "visual": {"SYMBOLIZES"},
    "knowledge_revelation": {"REVEALS", "KNOWS", "BELIEVES", "OBSERVES"},
}
NARRATIVE_KINDS = {"ACT", "ARC", "SEQUENCE", "BEAT", "SCENE", "EVENT", "DECISION", "REVELATION", "FORESHADOWING", "PAYOFF"}


def token(value):
    return str(getattr(value, "value", value)).upper()


def canonical(graph):
    nodes = {key: value for key, value in graph.nodes.items() if token(value.status) == "CANON"}
    edges = [edge for edge in graph.edges.values() if token(edge.status) == "CANON" and edge.source in nodes and edge.target in nodes]
    return nodes, edges


def _references(item):
    return list(dict.fromkeys([item.id, *[str(getattr(record, "source", record)) for record in item.evidence]]))


def analyze_attention(graph):
    """Return sparse entries, operational measurements and inspectable diagnostics.

    A declared graph edge is evidence of a declared relationship, not independent
    proof that a reader will experience it. Unsupported entries remain visible.
    Each dimension is stored as coordinate records; no N×N matrix is allocated.
    """
    nodes, edges = canonical(graph)
    ids = sorted(nodes)
    entries = {name: [] for name in RELATIONS}
    neighborhoods = defaultdict(set)
    strength = Counter()
    groups = defaultdict(list)
    unsupported = []
    attention_edges = []
    for edge in sorted(edges, key=lambda e: e.id):
        kind = token(edge.kind)
        categories = [name for name, kinds in RELATIONS.items() if kind in kinds]
        # A symbol is visual/emotional only when someone actually annotates it.
        if "visual" in categories and not any(nodes[x].attributes.get("visual_intent") or nodes[x].attributes.get("visual") for x in (edge.source, edge.target)):
            categories.remove("visual")
        if "emotional" in categories and not any(nodes[x].attributes.get("emotion") or nodes[x].attributes.get("emotional_target") for x in (edge.source, edge.target)):
            categories.remove("emotional")
        if not categories:
            continue
        attention_edges.append(edge)
        weight = max(0.0, float(edge.weight)) * float(edge.confidence)
        record = {"source": edge.source, "target": edge.target, "edge_id": edge.id, "edge_kind": kind, "strength": round(weight, 8), "confidence": edge.confidence, "evidence": _references(edge), "method": "declared_graph_relation"}
        for category in categories:
            entries[category].append(dict(record))
        neighborhoods[edge.source].add(edge.target)
        neighborhoods[edge.target].add(edge.source)
        strength[edge.source] += weight
        strength[edge.target] += weight
        groups[(edge.source, edge.target, kind)].append(edge.id)
        if not edge.evidence:
            unsupported.append(edge.id)
    pairs = {(edge.source, edge.target) for edge in attention_edges if edge.source != edge.target}
    n = len(nodes)
    possible = n * (n - 1)
    density = len(pairs) / possible if possible else 0.0
    total_strength = sum(strength.values())
    concentration = sum((value / total_strength) ** 2 for value in strength.values()) if total_strength else None
    events = sorted((node for node in nodes.values() if token(node.kind) in NARRATIVE_KINDS), key=lambda node: (node.order, node.id))
    continuity = []
    drift = []
    for a, b in zip(events, events[1:]):
        links = [edge.id for edge in attention_edges if {edge.source, edge.target} == {a.id, b.id}]
        shared = neighborhoods[a.id] & neighborhoods[b.id]
        union = neighborhoods[a.id] | neighborhoods[b.id]
        continuity.append({"source": a.id, "target": b.id, "direct_relation": bool(links), "evidence": links})
        drift.append({"source": a.id, "target": b.id, "neighborhood_change": 1 - len(shared) / len(union) if union else None, "evidence": sorted(union), "interpretation": "topological change; an intentional scene cut may also produce a high value"})
    setup = [edge for edge in edges if token(edge.kind) == "FORESHADOWS"]
    reversed_setups = [edge.id for edge in setup if nodes[edge.source].order >= nodes[edge.target].order]
    setup_nodes = [node.id for node in nodes.values() if token(node.kind) == "FORESHADOWING"]
    connected_setups = {edge.source for edge in setup} | {edge.target for edge in edges if token(edge.kind) == "PAYS_OFF"}
    high_dependency = 3
    overload = max(5, ceil(0.3 * max(0, n - 1)))
    underdeveloped = [node.id for node in nodes.values() if len(neighborhoods[node.id]) >= high_dependency and token(node.completion) not in {"COMPLETE", "APPROVED", "FINAL"} and not node.transition and not node.purpose.strip()]
    orphaned = sorted(node.id for node in nodes.values() if not neighborhoods[node.id])
    return {
        "method": "deterministic_sparse_typed_graph_projection",
        "scope": "CANON nodes and edges only",
        "node_order": ids,
        "sparse_matrices": entries,
        "metrics": {
            "attention_concentration": {"value": concentration, "definition": "Herfindahl concentration of incident declared strength, counted once per edge per endpoint; no preferred target"},
            "narrative_dependency_density": {"value": density, "edge_count": len(pairs), "possible_directed_pairs": possible, "definition": "Distinct directed attention pairs / N(N-1); self-loops excluded"},
            "sparse_dense_structure": {"density": density, "sparsity": 1 - density if possible else None, "definition": "Graph occupancy; neither density nor sparsity implies quality"},
            "attention_continuity": {"value": sum(item["direct_relation"] for item in continuity) / len(continuity) if continuity else None, "transitions": continuity, "definition": "Fraction of adjacent presentation-order narrative nodes joined by a declared attention edge"},
            "setup_to_payoff_connectivity": {"setup_edges": len(setup), "unconnected_setups": sorted(set(setup_nodes) - connected_setups), "nonforward_setup_edges": reversed_setups, "evidence": [edge.id for edge in setup], "definition": "FORESHADOWS: setup→payoff; PAYS_OFF: payoff→setup. Connectedness does not establish fairness or emotional success"},
            "attention_drift": {"transitions": drift, "definition": "One minus Jaccard similarity of adjacent narrative neighborhoods"},
            "redundant_attention": {"groups": [{"source": key[0], "target": key[1], "kind": key[2], "evidence": value} for key, value in sorted(groups.items()) if len(value) > 1], "definition": "Parallel edges of identical type/endpoints; multiple sources of evidence may justify them"},
            "orphaned_narrative_nodes": {"node_ids": orphaned, "intentional_sparse": [key for key in orphaned if nodes[key].attributes.get("intentional_sparsity")], "definition": "No incident attention relation; explicit intentional_sparsity annotation preserved"},
            "underdeveloped_high_dependency_nodes": {"node_ids": sorted(underdeveloped), "degree_threshold": high_dependency, "definition": "At least three distinct neighbors, unfinished annotation, no transition and no purpose; review prompt only"},
            "overloaded_narrative_nodes": {"node_ids": sorted(key for key in nodes if len(neighborhoods[key]) >= overload), "degree_threshold": overload, "definition": "Degree at least max(5, ceil(.3(N-1))); review prompt, not a defect verdict"},
        },
        "unsupported_edge_annotations": unsupported,
        "limitations": ["Only encoded relationships are measured; absent annotations are not proof of absent meaning.", "Emotion and visual attention require explicit node annotations.", "Declared edge weight times confidence is a heuristic, not a measured reader response.", "Proximity and semantic resemblance never create causal edges."],
    }
