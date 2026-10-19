"""Longitudinal voices and typed, time-indexed inter-thread relationships."""

from collections import Counter, defaultdict
from itertools import combinations

from .attention import _references, canonical, token


RELATION_TYPES = {
    "PARALLELS": "harmony", "CONTRASTS": "dissonance", "CONTRADICTS": "contradiction",
    "CAUSES": "complementarity", "ENABLES": "complementarity", "REQUIRES": "dependency",
    "MOTIVATES": "motivational_influence", "TRANSFORMS": "transformation", "REVEALS": "information_transfer",
    "FORESHADOWS": "delayed_resonance", "PAYS_OFF": "resolution", "SYMBOLIZES": "symbolic_reinforcement",
}


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def analyze_polyphony(graph):
    nodes, edges = canonical(graph)
    voices = defaultdict(list)
    for node in nodes.values():
        for thread in sorted(set(node.threads)):
            voices[thread].append(node)
    timeline = {}
    independence = []
    motifs = defaultdict(list)
    for thread, members in sorted(voices.items()):
        ordered = sorted(members, key=lambda node: (node.order, node.id))
        timeline[thread] = []
        member_ids = {node.id for node in members}
        causal = [edge.id for edge in edges if token(edge.kind) in {"CAUSES", "ENABLES", "REQUIRES", "MOTIVATES"} and edge.source in member_ids and edge.target in member_ids]
        for node in ordered:
            attrs = node.attributes
            knowledge = node.transition.knowledge_updates if node.transition else {}
            timeline[thread].append({"node_id": node.id, "time": node.time, "presentation_order": node.order, "revelation_order": node.revelation_order, "motivation": attrs.get("motivation"), "emotion": attrs.get("emotion", attrs.get("emotional_target")), "value_conflict": attrs.get("value_conflict"), "theme_progression": attrs.get("theme_progression", attrs.get("theme")), "knowledge_updates": knowledge, "motifs": _list(attrs.get("motifs")), "tension": attrs.get("tension"), "structural_purpose": node.purpose, "evidence": _references(node)})
        independence.append({"thread": thread, "exclusive_nodes": sorted(node.id for node in members if len(set(node.threads)) == 1), "internal_causal_edges": causal, "declared_motivations": sorted({str(node.attributes["motivation"]) for node in members if node.attributes.get("motivation")}), "assessment": "inspect independent motivation and causal development; thread count is not a score"})
    vertical = []
    diagonal = []
    convergence = []
    harmony = defaultdict(lambda: {"relations": Counter(), "evidence": []})
    interactions = Counter()
    for edge in sorted(edges, key=lambda edge: edge.id):
        relation = RELATION_TYPES.get(token(edge.kind))
        if not relation:
            continue
        a, b = nodes[edge.source], nodes[edge.target]
        for source_thread in sorted(set(a.threads)):
            for target_thread in sorted(set(b.threads)):
                if source_thread == target_thread:
                    continue
                row = {"time": max(a.order, b.order), "source_thread": source_thread, "target_thread": target_thread, "relation": relation, "edge_kind": token(edge.kind), "source": a.id, "target": b.id, "confidence": edge.confidence, "strength": max(0.0, edge.weight) * edge.confidence, "evidence": _references(edge), "aligned": a.order == b.order, "presentation_gap": abs(a.order - b.order), "diegetic_gap": abs(a.time - b.time)}
                vertical.append(row)
                if not row["aligned"]:
                    diagonal.append(dict(row))
                convergence.append({"source": source_thread, "target": target_thread, "via": [a.id, b.id], "relation": relation, "edge_id": edge.id})
                harmony[row["time"]]["relations"][relation] += 1
                harmony[row["time"]]["evidence"].append(edge.id)
                interactions[tuple(sorted((source_thread, target_thread)))] += 1
    # Shared scene membership is structural convergence, not ideological agreement.
    for node in sorted(nodes.values(), key=lambda node: (node.order, node.id)):
        for a, b in combinations(sorted(set(node.threads)), 2):
            convergence.append({"source": a, "target": b, "via": [node.id], "relation": "shared_narrative_node", "edge_id": None})
        for motif in _list(node.attributes.get("motifs")):
            motifs[str(motif)].append({"node_id": node.id, "time": node.order, "threads": node.threads, "transformation": node.attributes.get("motif_transformation"), "evidence": _references(node)})
    for edge in edges:
        if token(edge.kind) != "SYMBOLIZES":
            continue
        a, b = nodes[edge.source], nodes[edge.target]
        motif, occurrence = (a, b) if token(a.kind) == "MOTIF" else (b, a)
        if token(motif.kind) == "MOTIF":
            motifs[motif.id].append({"node_id": occurrence.id, "time": occurrence.order, "threads": occurrence.threads, "transformation": occurrence.attributes.get("motif_transformation"), "evidence": _references(edge)})
    motif_map = {}
    for key, occurrences in sorted(motifs.items()):
        grouped = {}
        for occurrence in occurrences:
            if occurrence["node_id"] in grouped:
                grouped[occurrence["node_id"]]["evidence"] = sorted(set(grouped[occurrence["node_id"]]["evidence"] + occurrence["evidence"]))
            else:
                grouped[occurrence["node_id"]] = dict(occurrence)
        motif_map[key] = sorted(grouped.values(), key=lambda item: (item["time"], item["node_id"]))
    redundant = []
    for a, b in combinations(sorted(voices), 2):
        left, right = {node.id for node in voices[a]}, {node.id for node in voices[b]}
        if left == right and left:
            redundant.append({"threads": [a, b], "evidence": sorted(left), "reason": "Identical node membership; inspect whether distinct voices are actually encoded"})
    return {"method": "deterministic_annotated_thread_projection", "alignment": "Presentation order; chronology and revelation order retained separately. Edges across orders remain explicitly diagonal.", "thread_timeline": timeline, "vertical_matrix": {"threads": sorted(voices), "entries": vertical, "definition": "Sparse typed H_ij(t), t=max(endpoint presentation orders); absent cells mean no encoded relation, not neutrality"}, "diagonal_dependencies": diagonal, "convergence_graph": convergence, "motif_recurrence": motif_map, "harmony_timeline": [{"time": time, "relations": dict(data["relations"]), "evidence": sorted(set(data["evidence"]))} for time, data in sorted(harmony.items())], "diagnostics": {"voice_independence": independence, "cross_thread_interactions": [{"threads": list(pair), "declared_relation_count": count} for pair, count in sorted(interactions.items())], "structural_redundancy": redundant, "unconnected_threads": sorted(thread for thread in voices if not any(thread in pair for pair in interactions)), "polyphony_score": None}, "limitations": ["Voice independence and thematic success require interpretation beyond graph membership.", "Dissonance and contradiction may be intentional artistic strengths.", "No reward is assigned for adding threads or increasing agreement.", "A resolution relation is declared PAYS_OFF evidence; whether the resolution is satisfying remains unmeasured."]}
