"""Behavioral checks for sparse evidence, separated clocks and honest evaluation."""

import json

import pytest

from narrative.analysis.attention import analyze_attention
from narrative.analysis.information_masking import analyze_information
from narrative.analysis.narrative_debt import analyze_debt
from narrative.analysis.polyphony import analyze_polyphony
from narrative.core.graph import StoryGraph
from narrative.core.schema import Edge, Evidence, Node, Project, State, Transition
from narrative.evaluation.adversarial import review
from narrative.evaluation.benchmarks import evaluate
from narrative.evaluation.calibration import aggregate, apply_human_ratings, pareto_front, weight_sensitivity


def story():
    return StoryGraph(Project(title="Three clocks", version="v1", initial_state=State(values={"world.open": False}), nodes=[
        Node(id="a", kind="Foreshadowing", label="A sees the seal", order=1, time=1, revelation_order=1, threads=["A"], attributes={"motivation": "preserve testimony", "motifs": ["seal"], "emotion": "anticipation", "visual_intent": "a divided seal"}, evidence=[Evidence(source="original:1", excerpt="The seal is split")]),
        Node(id="b", kind="Decision", label="B preserves water", order=1, time=1, revelation_order=2, threads=["B"], purpose="A costly commitment", attributes={"motivation": "save the district", "value_conflict": "duty versus truth", "stakes": "the district", "emotion": "resolve"}, transition=Transition(participants=["B"], effects={"world.open": True}, irreversible=["world.open"])),
        Node(id="c", kind="Scene", label="C conceals testimony", order=2, time=2, revelation_order=3, threads=["C"], attributes={"motivation": "preserve civic continuity", "theme": "stewardship"}),
        Node(id="payoff", kind="Payoff", label="The seal fails", order=9, time=9, revelation_order=9, threads=["A", "B"], attributes={"motifs": ["seal"], "motif_transformation": "private seal becomes public fracture"}),
        Node(id="seal", kind="Motif", label="Seal"),
        Node(id="secret", kind="Fact", label="The canal is a recorder"),
        Node(id="proposal", kind="Event", label="Unapproved miracle", status="PROPOSED", threads=["D"]),
    ], edges=[
        Edge(id="hint", source="a", target="payoff", kind="FORESHADOWS", evidence=[Evidence(source="original:1")]),
        Edge(id="contrast", source="a", target="b", kind="CONTRASTS", evidence=[Evidence(source="original:2")]),
        Edge(id="cause", source="b", target="payoff", kind="CAUSES"),
        Edge(id="opposition", source="b", target="c", kind="CONTRADICTS"),
        Edge(id="symbol", source="a", target="seal", kind="SYMBOLIZES"),
        Edge(id="proposed", source="proposal", target="payoff", kind="CAUSES", status="PROPOSED"),
    ]))


def test_sparse_attention_keeps_typed_evidence_and_excludes_proposals():
    graph = story()
    before = graph.document.model_dump_json()
    result = analyze_attention(graph)
    assert "proposal" not in result["node_order"]
    assert result["sparse_matrices"]["foreshadowing"][0]["evidence"] == ["hint", "original:1"]
    assert not any(item["edge_id"] == "contrast" for item in result["sparse_matrices"]["causal"])
    assert result["metrics"]["setup_to_payoff_connectivity"]["unconnected_setups"] == []
    assert result["metrics"]["narrative_dependency_density"]["edge_count"] == 5
    assert "secret" in result["metrics"]["orphaned_narrative_nodes"]["node_ids"]
    assert graph.document.model_dump_json() == before
    json.dumps(result)


def test_polyphony_preserves_dissonance_alignment_and_diagonal_evidence():
    result = analyze_polyphony(story())
    assert set(result["thread_timeline"]) == {"A", "B", "C"}
    contrast = next(item for item in result["vertical_matrix"]["entries"] if "contrast" in item["evidence"])
    assert contrast["relation"] == "dissonance" and contrast["aligned"]
    assert any("hint" in item["evidence"] for item in result["diagonal_dependencies"])
    assert [item["node_id"] for item in result["motif_recurrence"]["seal"]] == ["a", "payoff"]
    assert result["diagnostics"]["polyphony_score"] is None
    json.dumps(result)


def test_information_clocks_do_not_give_characters_future_audience_knowledge():
    graph = StoryGraph(Project(title="Flashback", initial_state=State(), nodes=[
        Node(id="learn", kind="Revelation", label="Learns later", time=8, order=1, revelation_order=1, transition=Transition(knowledge_updates={"A": ["secret"]}), attributes={"audience_knows": ["secret"]}),
        Node(id="act", kind="Decision", label="Acts too soon", time=2, order=2, revelation_order=2, transition=Transition(requires_knowledge={"A": ["secret"]})),
    ]))
    result = analyze_information(graph)
    assert result["unearned_knowledge"][0]["node_id"] == "act"
    assert result["audience_timeline"][0]["known"] == ["secret"]
    assert result["character_timeline"][0]["characters"] == {}


def test_audience_boolean_annotations_and_input_validation():
    graph = StoryGraph(Project(title="Boolean disclosure", nodes=[
        Node(id="public", kind="Fact", label="Public", revelation_order=1, attributes={"audience_knows": True}),
        Node(id="secret", kind="Fact", label="Secret", revelation_order=2, attributes={"audience_knows": False}),
    ]))
    assert analyze_information(graph)["audience_timeline"][-1]["known"] == ["public"]
    graph.update_node("secret", {"attributes": {"audience_knows": [42]}})
    with pytest.raises(ValueError, match="audience knowledge"):
        analyze_information(graph)


def test_failed_transitions_cannot_grant_knowledge_or_reveal_secret():
    graph = StoryGraph(Project(title="Failed revelation", initial_state=State(values={"world.open": False}), nodes=[
        Node(id="fail", kind="Revelation", label="Blocked revelation", time=1, revelation_order=1, transition=Transition(requires={"world.open": True}, knowledge_updates={"A": ["secret"]})),
        Node(id="act", kind="Decision", label="Unsupported action", time=2, revelation_order=2, transition=Transition(requires_knowledge={"A": ["secret"]}, exceptions=["unestablished_excuse"])),
        Node(id="secret", kind="Fact", label="Hidden testimony", revelation_order=3),
    ], edges=[Edge(id="reveal", source="fail", target="secret", kind="REVEALS")]))
    result = analyze_information(graph)
    assert all(not item["characters"].get("A") for item in result["character_timeline"])
    assert result["unearned_knowledge"][0]["node_id"] == "act"
    assert result["audience_timeline"][-1]["known"] == []
    assert result["unexecuted_revelations"] == [{"node_id": "fail", "fact_id": "secret", "edge_id": "reveal"}]


def test_benchmarks_report_nine_dimensions_and_never_fabricate_reader_scores():
    result = evaluate(story())
    assert set(result["dimensions"]) == {f"B{i}" for i in range(1, 10)}
    assert all(metric["model_score"] is None for metric in result["dimensions"].values())
    assert result["dimensions"]["B8"]["observations"]["comparative_originality"]["value"] is None
    assert result["weighted_aggregate"] is None
    assert len(result["safeguards"]) == 11
    assert result["measurement_groups"]["subjective"]
    assert result["calibration"]["status"] == "UNCALIBRATED"
    json.dumps(result)


def test_human_override_preserves_model_and_rejects_stale_ratings():
    report = evaluate(story())
    report["dimensions"]["B4"]["model_score"] = 1.0
    ratings = [{"metric_id": "B4", "score": 3, "evaluator": "author", "rationale": "A reader identified a supported emotional turn", "version": "v1"}]
    updated = apply_human_ratings(report, ratings)
    assert updated["quality_vector"]["B4"] == 3
    assert updated["dimensions"]["B4"]["model_score"] == 1
    assert report["dimensions"]["B4"]["human_score"] is None
    with pytest.raises(ValueError, match="stale"):
        apply_human_ratings(report, [{**ratings[0], "version": "old"}])


def test_preferences_expose_tradeoffs_and_missing_judgments():
    vectors = {"a": {"B1": 4, "B4": 1}, "b": {"B1": 1, "B4": 4}, "c": {"B1": 0, "B4": 0}}
    assert pareto_front(vectors) == ["a", "b"]
    sensitivity = weight_sensitivity(vectors, {"B1": 1, "B4": 1})
    assert any(item["ranking_changed"] for item in sensitivity["perturbations"])
    with pytest.raises(ValueError):
        aggregate({"B1": None}, {"B1": 1})
    with pytest.raises(ValueError):
        pareto_front({"a": {"B1": 2}, "b": {"B1": None}})


def test_unconnected_setup_and_intentional_open_ending_remain_distinct():
    graph = StoryGraph(Project(title="Open", nodes=[Node(id="promise", kind="Foreshadowing", label="An open promise", attributes={"intentional_open_end": True})]))
    result = analyze_debt(graph)
    assert result["open_count"] == 1 and result["unintentional_count"] == 0


def test_adversarial_roles_preserve_reader_perspectives_and_no_winner():
    result = review(story())
    assert len(result["failure_mode_checks"]) == 12
    assert result["roles"]["judge"]["winner"] is None
    assert result["perspectives"]["first_time"]["reader_score"] is None
    assert result["perspectives"]["expert"]["reader_score"] is None
    assert result["perspectives"]["discrepancy"]["averaged_score"] is None
    assert result["provenance"]["model_calls"] == 0
    json.dumps(result)


def test_empty_story_analysis_is_explicitly_undefined_and_json_serializable():
    graph = StoryGraph(Project(title="Empty"))
    assert analyze_attention(graph)["metrics"]["attention_concentration"]["value"] is None
    assert analyze_polyphony(graph)["thread_timeline"] == {}
    assert evaluate(graph)["dimensions"]["B4"]["model_score"] is None
    json.dumps(review(graph))
