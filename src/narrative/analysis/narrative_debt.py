"""Explicit unresolved obligations, without interpreting unresolvedness as failure."""

from .attention import _references, canonical, token


def analyze_debt(graph):
    nodes, edges = canonical(graph)
    resolved_setups = {edge.source for edge in edges if token(edge.kind) == "FORESHADOWS"} | {edge.target for edge in edges if token(edge.kind) == "PAYS_OFF"}
    debts = []
    for node in sorted(nodes.values(), key=lambda node: node.id):
        explicit = node.attributes.get("unresolved_debt")
        missing_payoff = token(node.kind) == "FORESHADOWING" and node.id not in resolved_setups
        if explicit or missing_payoff:
            debts.append({"node_id": node.id, "kind": "explicit_obligation" if explicit else "unconnected_setup", "description": str(explicit or "No declared payoff relationship"), "intentional": bool(node.attributes.get("intentional_open_end")), "evidence": _references(node)})
    return {"obligations": debts, "open_count": len(debts), "unintentional_count": sum(not debt["intentional"] for debt in debts), "definition": "Declared unresolved_debt annotations and Foreshadowing nodes without FORESHADOWS/PAYS_OFF connectivity", "limitation": "Connected payoff edges establish encoding, not reader satisfaction; intentional open endings are retained."}
