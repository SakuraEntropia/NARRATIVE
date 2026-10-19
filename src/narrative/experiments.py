"""Executable A–G experiments on original fixtures, with factual telemetry."""

from __future__ import annotations

import json
import time
from pathlib import Path

from narrative.analysis.attention import analyze_attention
from narrative.analysis.polyphony import analyze_polyphony
from narrative.core.graph import StoryGraph
from narrative.core.schema import Project
from narrative.core.state_machine import simulate
from narrative.examples import example_graph
from narrative.memory import DependencyCache, estimate_units, retrieve
from narrative.optimization import DEPENDENCY_TYPES, Pivot, affected_nodes, backward_influence, evaluate_pivot, propose_pivots
from narrative.refinement import refine


def _without_thread(graph: StoryGraph, thread: str) -> StoryGraph:
    document = graph.document
    removed = {node.id for node in document.nodes if node.threads == [thread]}
    kept = []
    for node in document.nodes:
        if node.id in removed:
            continue
        node.threads = [item for item in node.threads if item != thread]
        kept.append(node)
    document.nodes = kept
    document.edges = [edge for edge in document.edges if edge.source not in removed and edge.target not in removed]
    return StoryGraph(document)


def _long_range_signature(graph: StoryGraph, target: str) -> list[tuple[str, str, str]]:
    return sorted((edge.source, edge.target, str(edge.kind)) for edge in graph.edges.values()
                  if str(edge.kind) in {"FORESHADOWS", "PAYS_OFF"} and target in {edge.source, edge.target})


def _required_predecessors(graph: StoryGraph, target: str) -> set[str]:
    """Independent unbounded graph oracle for this small experiment only."""
    required, queue = {target}, [target]
    while queue:
        current = queue.pop()
        for edge in graph.edges.values():
            other = None
            if edge.target == current and str(edge.kind) in DEPENDENCY_TYPES:
                other = edge.source
            elif str(edge.kind) in {"FORESHADOWS", "PAYS_OFF"}:
                if edge.target == current:
                    other = edge.source
                elif edge.source == current:
                    other = edge.target
            if other is not None and other not in required:
                required.add(other)
                queue.append(other)
    return required


def run_experiments(output_dir: str | Path | None = None) -> dict:
    """Run real offline computations; optionally save a reproducible JSON report."""
    from narrative.evaluation.adversarial import review
    from narrative.evaluation.benchmarks import evaluate

    started = time.perf_counter()
    graph = example_graph()
    results = {}

    stage = time.perf_counter()
    refined = refine(graph, "ACT_1", depth=2, max_nodes=6)
    parent_constraint_ids = {constraint.id for constraint in graph.get("ACT_1").hard_constraints}
    inheritance = [{"node_id": node_id,
                    "constraint_ids": [constraint.id for constraint in refined.graph.get(node_id).hard_constraints],
                    "status": str(refined.graph.get(node_id).status)} for node_id in refined.children]
    results["A"] = {
        "name": "Recursive refinement", "created_nodes": inheritance,
        "constraints_preserved": bool(inheritance) and all(parent_constraint_ids <= set(item["constraint_ids"]) for item in inheritance),
        "checkpoints": refined.checkpoints, "feedback": refined.feedback,
        "stop_reason": refined.stopped_reason, "telemetry": refined.telemetry.model_dump(),
        "source_unchanged": len(graph.nodes) == len(example_graph().nodes),
        "method": "deterministic template proposals, not creative model output",
        "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    defective = example_graph("weak_motivation")
    original_document = defective.document.model_dump(mode="json")
    candidates = propose_pivots(defective, "CLIMAX", max_candidates=3)
    revisions = [evaluate_pivot(defective, candidate)["report"] for candidate in candidates]
    results["B"] = {
        "name": "Backward propagation", "defect_evaluation": evaluate(defective)["safeguards"]["character_motivation_consistency"],
        "backward_influence": backward_influence(defective, "CLIMAX"),
        "candidate_reports": revisions, "original_unchanged": defective.document.model_dump(mode="json") == original_document,
        "observed_proxy_repairs": [report["expected_improvement"] for report in revisions],
        "limitation": "Repairs restore authored motivation evidence; persuasive emotional improvement has not been established.",
        "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    without_sera = _without_thread(graph, "sera")
    full_polyphony, reduced_polyphony = analyze_polyphony(graph), analyze_polyphony(without_sera)
    lost_nodes = sorted(set(graph.nodes) - set(without_sera.nodes))
    reduced_simulation = simulate(without_sera)
    results["C"] = {
        "name": "Polyphony and thread removal", "full": full_polyphony, "without_sera": reduced_polyphony,
        "lost_nodes": lost_nodes,
        "lost_contribution": {"perspective": "Civic continuity conflicts with immediate disclosure",
                              "causal_node": "SERA_CONCEDES", "consequence": "CLIMAX requires the signed correction produced by this thread",
                              "regression_findings": [finding.model_dump(mode="json") for finding in reduced_simulation.findings]},
        "quality_preference": None, "limitation": "The intervention removes represented contributions; it does not establish that more threads make better fiction.",
        "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    complex_graph = example_graph("complex_low_agency")
    simple_benchmark, complex_benchmark = evaluate(graph), evaluate(complex_graph)
    results["D"] = {
        "name": "Complexity versus agency", "version_A": {"description": "More rules, fewer participant-driven decisions", "node_count": len(complex_graph.nodes), "benchmark": complex_benchmark, "critique": review(complex_graph)},
        "version_B": {"description": "Fewer rules, authored consequential choices", "node_count": len(graph.nodes), "benchmark": simple_benchmark, "critique": review(graph)},
        "automatic_artistic_ranking": None,
        "evidence": {"complex_agency": complex_benchmark["safeguards"]["character_agency"],
                     "simple_agency": simple_benchmark["safeguards"]["character_agency"],
                     "complex_unused_rules": complex_benchmark["dimensions"]["B2"]["observations"]["unused_elements"]},
        "claim": "Additional worldbuilding yields observations and counterevidence, not an automatic score gain.",
        "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    context = retrieve(graph, ["PAYOFF"], token_budget=60_000, max_nodes=64, max_hops=16)
    setup, payoff = graph.get("FUSE_IMAGE"), graph.get("PAYOFF")
    between = [node.id for node in graph.nodes.values() if setup.order < node.order < payoff.order and node.kind in {"Scene", "Event", "Decision", "Revelation"}]
    results["E"] = {
        "name": "Long-range attention", "setup": setup.id, "payoff": payoff.id,
        "intervening_narrative_nodes": between, "retrieved_node_ids": context.node_ids,
        "setup_retrieved": setup.id in context.node_ids, "context_overflow": context.overflow,
        "dependency_signature": _long_range_signature(graph, "PAYOFF"),
        "attention": analyze_attention(graph)["metrics"]["setup_to_payoff_connectivity"],
        "telemetry": context.telemetry.model_dump(), "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    rule = graph.get("FUSE_RULE")
    changed_transition = rule.transition.model_dump(mode="json")
    changed_transition["effects"]["world.manual_gate_allowed"] = False
    regression_pivot = Pivot(id="remove_manual_gate", target="CLIMAX", node_id="FUSE_RULE",
                             changes={"transition": changed_transition}, evidence=["FUSE_RULE", "PREPARE_GATE"],
                             kind="world_rule_change", cost=2, confidence=1)
    regression = evaluate_pivot(graph, regression_pivot)["report"]
    results["F"] = {
        "name": "World-rule regression", "changed_node": "FUSE_RULE",
        "affected_closure": affected_nodes(graph, ["FUSE_RULE"]),
        "branch_valid": regression["valid"], "regression_findings": regression["regression_risks"],
        "simulation": regression["simulation"], "canonical_approval": False,
        "latency_seconds": time.perf_counter() - stage,
    }

    stage = time.perf_counter()
    repeats = 5
    full_start = time.perf_counter()
    full_signatures = []
    full_units = 0
    for _ in range(repeats):
        full_units += estimate_units(graph.document)
        full_signatures.append(_long_range_signature(graph, "PAYOFF"))
    full_latency = time.perf_counter() - full_start
    incremental_start = time.perf_counter()
    cache = DependencyCache()
    incremental_signatures, contexts = [], []
    incremental_units = 0
    for _ in range(repeats):
        cached = cache.get("payoff_signature")
        if cached is None:
            retrieved = retrieve(graph, ["PAYOFF"], token_budget=60_000, max_nodes=64, max_hops=16)
            contexts.append(retrieved)
            incremental_units += retrieved.estimated_tokens
            partial = StoryGraph(Project(title=graph.document.title, nodes=retrieved.nodes, edges=retrieved.edges))
            # This query only inspects dependency endpoints; partial state is not
            # used to claim equivalence of complete-story simulation or judgment.
            cached = _long_range_signature(partial, "PAYOFF")
            cache.set("payoff_signature", cached, dependencies=retrieved.node_ids)
        incremental_signatures.append(cached)
    incremental_latency = time.perf_counter() - incremental_start
    required = _required_predecessors(graph, "PAYOFF")
    retrieved_ids = set(contexts[0].node_ids)
    missing = sorted(required - retrieved_ids)
    constrained = retrieve(graph, ["PAYOFF"], token_budget=20, max_nodes=2, max_hops=0)
    cache.set("unrelated_character", {"node": "SERA"}, dependencies=["SERA"])
    invalidated = cache.invalidate(["FUSE_RULE"], graph)
    results["G"] = {
        "name": "Context estimates and cache correctness", "repeated_query": "PAYOFF's explicit setup/payoff edge endpoints", "repeats": repeats,
        "full_context": {"estimated_context_units": full_units, "latency_seconds": full_latency},
        "incremental": {"estimated_context_units": incremental_units, "latency_seconds": incremental_latency,
                        "cache_hits": cache.hits, "retrieved_node_ids": sorted(retrieved_ids)},
        "equivalent_query_results": full_signatures == incremental_signatures,
        "required_dependency_oracle": sorted(required), "missing_dependencies": missing,
        "missed_dependency_rate": len(missing) / len(required) if required else 0,
        "bounded_failure": {"overflow": constrained.overflow, "warnings": constrained.warnings, "usable": not constrained.overflow},
        "invalidation": {"changed": ["FUSE_RULE"], "removed_cache_keys": invalidated,
                         "unrelated_entry_preserved": cache.get("unrelated_character") is not None},
        "actual_model_usage": {"prompt_tokens": 0, "completion_tokens": 0, "api_calls": 0, "cost_usd": 0},
        "estimate_method": contexts[0].telemetry.estimate_method,
        "limitations": ["UTF-8 context units are not actual billed model tokens.",
                        "Query equivalence and missed-dependency rate cover this encoded dependency query on one synthetic fixture.",
                        "No semantic or artistic quality equivalence is claimed; incremental retrieval may be slower for small graphs.",
                        "Cache correctness depends on declared dependencies; full audits remain necessary."],
        "latency_seconds": time.perf_counter() - stage,
    }
    report = {
        "dataset": "The Last Tide Ledger", "dataset_origin": "original synthetic, explicitly authored AI-assisted fixtures",
        "experiments": results,
        "checks": {
            "A_constraints_inherited": results["A"]["constraints_preserved"],
            "B_multiple_valid_repairs": len(revisions) >= 2 and all(item["valid"] for item in revisions),
            "B_source_immutable": results["B"]["original_unchanged"],
            "C_three_voices": len(full_polyphony["thread_timeline"]) == 3,
            "D_complexity_not_scored": complex_benchmark["weighted_aggregate"] is None,
            "E_setup_retrieved": results["E"]["setup_retrieved"] and not context.overflow,
            "F_regression_detected": not regression["valid"] and bool(regression["regression_risks"]),
            "G_query_equivalent": results["G"]["equivalent_query_results"],
            "G_overflow_explicit": constrained.overflow,
        },
        "total_latency_seconds": time.perf_counter() - started,
        "research_status": "Engineering mechanisms exercised offline; no validated artistic improvement, calibrated reader judgment or paid-model experiment.",
    }
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "experiments.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
