import pytest

from narrative.core.graph import GraphError
from narrative.core.schema import CanonStatus, Edge, Node
from narrative.core.state_machine import simulate
from narrative.examples import example_graph
from narrative.optimization import (
    Pivot, affected_nodes, backward_influence, duel, evaluate_pivot,
    pareto_select, propose_pivots,
)


def test_original_story_is_consistent_and_has_irreversible_choice():
    graph = example_graph()
    result = simulate(graph)
    assert not result.findings
    assert result.state.values["world.district_safe"] is True
    assert result.state.values["resource.fuse.intact"] is False
    assert "character.mara.anonymous" in result.state.irreversible
    assert "TESTIMONY" not in result.applied
    assert "world.archive_waterproof" not in result.state.values


def test_backward_search_does_not_treat_symbolism_as_causal_proof():
    influence = backward_influence(example_graph(), "CLIMAX")
    root_ids = {item["node_id"] for item in influence["candidate_root_causes"]}
    assert {"FUSE_RULE", "PROMISE", "PREPARE_GATE"} <= root_ids
    assert "THEME" not in root_ids
    assert any(item["source"] == "THEME" and item["kind"] == "SYMBOLIZES" for item in influence["associations"])


def test_unsupported_dependency_is_not_advanced_as_evidence():
    graph = example_graph()
    graph.add_edge(Edge(id="unsupported", source="BLACK_GLASS", target="CLIMAX", kind="CAUSES"))
    influence = backward_influence(graph, "CLIMAX")
    assert "BLACK_GLASS" not in {item["node_id"] for item in influence["candidate_root_causes"]}
    assert any(item["edge_id"] == "unsupported" for item in influence["unsupported_dependencies"])


def test_backward_search_recovers_explicit_knowledge_provider_after_lost_motivation_link():
    graph = example_graph("weak_motivation")
    influence = backward_influence(graph, "CLIMAX")
    assert any(item["node_id"] == "PROMISE" and item["relation"] == "KNOWLEDGE_PRECONDITION"
               for item in influence["candidate_root_causes"])
    assert any(item["source"] == "PROMISE" and item["target"] == "CLIMAX"
               for item in influence["transition_dependencies"])


def test_pivot_evaluates_counterfactual_without_promoting_or_mutating():
    graph = example_graph("weak_motivation")
    before = graph.document.model_dump(mode="json")
    candidates = propose_pivots(graph, "CLIMAX")
    assert len(candidates) >= 2
    outcome = evaluate_pivot(graph, candidates[0])
    assert outcome["branch"].get("CLIMAX").status == CanonStatus.PROPOSED
    assert outcome["report"]["valid"]
    assert not outcome["report"]["canonical_approval"]
    assert outcome["report"]["simulation"]["state"]["values"]["world.district_safe"]
    assert outcome["report"]["expected_improvement"]["unsupported_decisions_removed"] == 1
    assert outcome["report"]["expected_improvement"]["artistic_improvement"] is None
    assert graph.document.model_dump(mode="json") == before


def test_explicit_approval_only_promotes_the_isolated_branch():
    graph = example_graph("weak_motivation")
    candidate = propose_pivots(graph, "CLIMAX")[0]
    outcome = evaluate_pivot(graph, candidate, approve=True)
    assert outcome["branch"].get("CLIMAX").status == CanonStatus.CANON
    assert outcome["report"]["canonical_approval"]
    assert not graph.get("CLIMAX").attributes.get("motivation")


def test_locked_canon_requires_specific_node_authorization():
    graph = example_graph("weak_motivation")
    graph.update_node("CLIMAX", {"locked": True})
    candidate = propose_pivots(graph, "CLIMAX")[0]
    with pytest.raises(GraphError, match="Locked"):
        evaluate_pivot(graph, candidate, approve=True)
    outcome = evaluate_pivot(graph, candidate, approve=True, authorized_locked=["CLIMAX"])
    assert outcome["report"]["valid"]
    assert graph.get("CLIMAX").locked


def test_early_rule_change_reports_future_prerequisite_and_local_invariant():
    graph = example_graph()
    transition = graph.get("FUSE_RULE").transition.model_dump(mode="json")
    transition["effects"]["world.manual_gate_allowed"] = False
    pivot = Pivot(id="break_gate", target="CLIMAX", node_id="FUSE_RULE",
                  changes={"transition": transition}, evidence=["FUSE_RULE"])
    result = evaluate_pivot(graph, pivot)["report"]
    assert not result["valid"]
    codes = {item["code"] for item in result["regression_risks"]}
    assert {"PRECONDITION", "LOCAL_INVARIANT"} <= codes
    assert {"PREPARE_GATE", "CLIMAX", "PAYOFF"} <= set(result["affected_nodes"])
    assert graph.get("FUSE_RULE").transition.effects["world.manual_gate_allowed"] is True


def test_candidate_pool_and_backward_traversal_are_bounded():
    graph = example_graph("weak_motivation")
    assert len(propose_pivots(graph, "CLIMAX", max_candidates=1)) == 1
    assert not propose_pivots(graph, "CLIMAX", max_candidates=0)
    assert not backward_influence(graph, "CLIMAX", max_depth=0)["candidate_root_causes"]
    with pytest.raises(ValueError):
        propose_pivots(graph, "CLIMAX", max_candidates=101)


def test_untrusted_candidate_fields_and_absent_evidence_rejected():
    graph = example_graph("weak_motivation")
    candidate = propose_pivots(graph, "CLIMAX")[0]
    bad = candidate.model_copy(update={"changes": {"locked": False}})
    with pytest.raises(ValueError, match="Unsupported"):
        evaluate_pivot(graph, bad)
    absent = candidate.model_copy(update={"evidence": ["not_a_node"]})
    with pytest.raises(ValueError, match="evidence"):
        evaluate_pivot(graph, absent)


def test_pareto_retains_tradeoffs_and_excludes_hard_invalid_branches():
    reports = [
        {"pivot": {"id": "cheap"}, "valid": True, "objectives": {"hard_errors": 0, "defects": 2, "cost": 1}},
        {"pivot": {"id": "thorough"}, "valid": True, "objectives": {"hard_errors": 0, "defects": 0, "cost": 3}},
        {"pivot": {"id": "dominated"}, "valid": True, "objectives": {"hard_errors": 0, "defects": 3, "cost": 2}},
        {"pivot": {"id": "invalid"}, "valid": False, "objectives": {"hard_errors": 1, "defects": 0, "cost": 0}},
    ]
    assert set(pareto_select(reports)) == {"cheap", "thorough"}


def test_duel_stops_and_does_not_accept_a_branch():
    graph = example_graph("weak_motivation")
    result = duel(graph, target="CLIMAX", max_candidates=2, max_iterations=2)
    assert result["iterations"] <= 2
    assert len(result["candidates"]) == 2
    assert result["pareto_set"]
    assert not graph.get("CLIMAX").attributes.get("motivation")
    assert all(not candidate["canonical_approval"] for candidate in result["candidates"])


def test_state_dependency_closure_finds_unlinked_future_use():
    graph = example_graph()
    payload = graph.get("PAYOFF").model_dump(mode="json")
    payload.update({
        "id": "LATER", "time": 30, "parent_id": None,
        "transition": {"requires": {"resource.fuse.intact": False}},
    })
    graph.add_node(Node.model_validate(payload))
    assert "LATER" in affected_nodes(graph, ["CLIMAX"])


def test_experiments_a_through_g_have_real_outputs():
    from narrative.experiments import run_experiments

    report = run_experiments()
    assert set(report["experiments"]) == set("ABCDEFG")
    assert all(report["checks"].values()), report["checks"]
    assert report["experiments"]["G"]["actual_model_usage"]["api_calls"] == 0
    assert report["experiments"]["E"]["intervening_narrative_nodes"]
    measurement = report["experiments"]["G"]
    assert measurement["missed_dependency_rate"] == len(measurement["missing_dependencies"]) / len(measurement["required_dependency_oracle"])
