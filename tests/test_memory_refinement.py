"""Failure-oriented tests for bounded proposals, evidence retrieval and budgets."""

import pytest
from pydantic import BaseModel

from narrative.core.graph import StoryGraph
from narrative.core.schema import Constraint, Edge, Node, Project, State, Transition
from narrative.memory import Budget, BudgetExceeded, DependencyCache, Telemetry, retrieve
from narrative.providers import CallableProvider, ProviderOutputError, ProviderResponse, structured_generate
from narrative.refinement import refine


def project():
    constraint = Constraint(id="medium", key="medium", expected="screen", scope="design")
    return StoryGraph(Project(title="Archive", constraints=[constraint], nodes=[
        Node(id="story", kind="Story", label="Archive", attributes={"medium": "screen"},
             hard_constraints=[Constraint(id="truth", key="world.archive_exists", expected=True)]),
        Node(id="act", kind="Act", label="Discovery", parent_id="story", level=4,
             attributes={"medium": "screen"}, purpose="Discover a withheld record"),
    ]))


def test_refinement_is_bounded_isolated_inherits_and_stays_proposed():
    graph = project()
    before = graph.document.model_dump()
    result = refine(graph, "act", depth=8, max_nodes=5)
    assert graph.document.model_dump() == before
    assert len(result.children) == 5
    assert result.stopped_reason == "node_limit"
    for identifier in result.children:
        child = result.graph.get(identifier)
        assert child.status == "PROPOSED"
        assert {item.id for item in child.hard_constraints} == {"medium", "truth"}
        assert child.attributes["medium"] == "screen"
        assert child.attributes["requires_authoring"] is True
    assert all(not item["applied"] for item in result.feedback)
    assert result.telemetry.prompt_tokens == result.telemetry.completion_tokens == 0
    assert result.telemetry.estimated_api_cost_usd == 0
    assert result.telemetry.estimated_context_units > 0


def test_declared_low_information_gain_terminates_before_installing_children():
    provider = CallableProvider("low-gain", lambda request: {
        "children": [{"label": "Duplicate", "purpose": "Duplicate details"}],
        "information_gain": 0.0, "feedback": [], "uncertainty": "No new information",
    }, live=False)
    result = refine(project(), "act", provider=provider)
    assert not result.children
    assert result.checkpoints[0]["reason"] == "information_gain_threshold"
    assert result.telemetry.calls == 1


def test_inherited_invariant_violation_rejects_parent_decomposition_atomically():
    graph = project()
    provider = CallableProvider("conflicting", lambda request: {
        "children": [{"label": "Erase archive", "purpose": "Contradict the invariant",
                      "transition": {"effects": {"world.archive_exists": False}}}],
        "information_gain": 0.5, "feedback": ["Consider changing the ancestor"],
        "uncertainty": "Candidate requires review",
    }, live=False)
    result = refine(graph, "act", provider=provider)
    assert result.stopped_reason == "validation_rejected"
    assert not result.children
    assert result.graph.document == graph.document
    assert all(item["applied"] is False for item in result.feedback)


def test_bad_provider_has_finite_retries_and_no_graph_mutation():
    invocations = []
    provider = CallableProvider("bad", lambda request: invocations.append(request) or {"garbage": 1}, live=False)
    result = refine(project(), "act", provider=provider, max_retries=1)
    assert result.stopped_reason == "provider_output_invalid"
    assert not result.children
    assert len(invocations) == 2
    assert "validation_feedback" in invocations[1]
    assert result.telemetry.retries == 1


def test_refinement_exhaustion_is_partial_and_explicit():
    result = refine(project(), "act", budget=Budget(max_calls=0))
    assert result.stopped_reason == "budget_exhausted"
    assert not result.children
    assert result.telemetry.calls == 0
    result = refine(project(), "act", token_budget=1)
    assert result.stopped_reason == "context_overflow"
    assert result.telemetry.calls == 0


def test_retrieval_preserves_upstream_long_range_evidence_rules_and_knowledge():
    graph = project()
    graph.add_node(Node(id="Mara", kind="Character", label="Mara", attributes={"medium": "screen"}))
    graph.add_node(Node(id="rule", kind="Rule", label="Only an owner can read", attributes={"medium": "screen", "global": True}))
    graph.add_node(Node(id="setup", kind="Scene", label="A key is entrusted", level=7,
                        attributes={"medium": "screen"}, evidence=[{"source": "author", "excerpt": "Original key scene"}]))
    graph.add_node(Node(id="upstream", kind="Scene", label="Open the door", level=7,
                        attributes={"medium": "screen"}))
    graph.add_node(Node(id="payoff", kind="Scene", label="Read the record", level=7, parent_id="act",
                        attributes={"medium": "screen"}, transition=Transition(participants=["Mara"],
                        requires={"world.door_open": True}, requires_knowledge={"Mara": ["key"]})))
    graph.add_edge(Edge(id="causal", source="upstream", target="payoff", kind="CAUSES"))
    graph.add_edge(Edge(id="long", source="setup", target="payoff", kind="PAYS_OFF"))
    document = graph.document
    document.initial_state = State(values={"world.door_open": False}, knowledge={"Mara": ["key"]})
    graph = StoryGraph(document)
    result = retrieve(graph, ["payoff"], token_budget=100_000)
    assert not result.overflow
    assert {"payoff", "setup", "upstream", "Mara", "rule"} <= set(result.node_ids)
    assert {item["constraint"]["id"] for item in result.hard_constraints} == {"medium", "truth"}
    assert result.state["knowledge"]["Mara"] == ["key"]
    assert any(node["id"] == "setup" and node["evidence"] for node in result.nodes)


def test_required_context_overflow_is_explicit_and_expansion_bounded():
    graph = project()
    result = retrieve(graph, "act", token_budget=1)
    assert result.overflow
    assert result.hard_constraints
    for index in range(10):
        graph.add_node(Node(id=f"source{index}", kind="Fact", label="Evidence", attributes={"medium": "screen"}))
        graph.add_edge(Edge(id=f"edge{index}", source=f"source{index}", target="act", kind="REQUIRES"))
    result = retrieve(graph, "act", token_budget=100_000, max_nodes=3)
    assert result.overflow
    assert len(result.nodes) <= 3
    assert result.omitted_ids


def test_dependency_cache_invalidates_closure_and_summary_but_keeps_unrelated():
    graph = project()
    graph.add_node(Node(id="downstream", kind="Fact", label="Dependent", attributes={"medium": "screen"}))
    graph.add_edge(Edge(id="causal", source="act", target="downstream", kind="CAUSES"))
    graph.add_node(Node(id="sibling", kind="Act", label="Other act", parent_id="story", level=4,
                        attributes={"medium": "screen"}))
    cache = DependencyCache()
    cache.set("score", {"value": [1]}, dependencies=["downstream"])
    cache.set("summary", "summary", dependencies=["story"])
    cache.set("unrelated", "untouched", dependencies=["sibling"])
    returned = cache.get("score")
    returned["value"].append(2)
    assert cache.get("score") == {"value": [1]}
    assert cache.invalidate(["act"], graph) == ["score", "summary"]
    assert cache.get("unrelated") == "untouched"
    assert cache.invalidate([], graph, full_audit=True) == ["unrelated"]


def test_changed_parent_invalidates_child_constraints_but_child_does_not_evict_sibling():
    graph = project()
    for identifier in ("child", "sibling"):
        graph.add_node(Node(id=identifier, kind="Scene", label=identifier, parent_id="act", level=7,
                            attributes={"medium": "screen"}))
        graph.add_edge(Edge(id=f"parent-{identifier}", source=identifier, target="act", kind="BELONGS_TO"))
    cache = DependencyCache()
    cache.set("child", "value", ["child"])
    cache.set("sibling", "value", ["sibling"])
    cache.set("summary", "value", ["act"])
    assert cache.invalidate(["child"], graph) == ["child", "summary"]
    assert cache.get("sibling") == "value"
    cache.set("child", "value", ["child"])
    assert cache.invalidate(["act"], graph) == ["child", "sibling"]


def test_hypothetical_summary_retains_status_and_original_evidence():
    graph = project()
    graph.add_node(Node(id="source", kind="Fact", label="Original passage", attributes={"medium": "screen"},
                        evidence=[{"source": "author", "excerpt": "Exact source passage"}]))
    graph.add_node(Node(id="summary", kind="Hypothesis", label="Possible reading", status="HYPOTHETICAL",
                        attributes={"summary_of": ["source"]}, evidence=[{"source": "model", "node_id": "source"}],
                        hard_constraints=[Constraint(id="tentative", key="interpretation", expected="possible", scope="design")]))
    result = retrieve(graph, "summary", token_budget=100_000)
    assert not result.overflow
    by_id = {node["id"]: node for node in result.nodes}
    assert by_id["summary"]["status"] == "HYPOTHETICAL"
    assert by_id["source"]["evidence"][0]["excerpt"] == "Exact source passage"
    assert result.hard_constraints[-1]["source_status"] == "HYPOTHETICAL"


def test_motivating_character_and_revelation_dependencies_expand_upstream():
    graph = project()
    for identifier in ("choice", "motive", "knowledge", "source"):
        graph.add_node(Node(id=identifier, kind="Scene", label=identifier,
                            attributes={"medium": "screen"}))
    graph.add_edge(Edge(id="motivation", source="motive", target="choice", kind="MOTIVATES"))
    graph.add_edge(Edge(id="reveal", source="knowledge", target="motive", kind="REVEALS"))
    graph.add_edge(Edge(id="cause", source="source", target="knowledge", kind="CAUSES"))
    result = retrieve(graph, "choice", token_budget=100_000)
    assert not result.overflow
    assert {"choice", "motive", "knowledge", "source"} <= set(result.node_ids)
    limited = retrieve(graph, "choice", token_budget=100_000, max_hops=1)
    assert limited.overflow


def test_hierarchical_budget_checks_all_scopes_before_mutation():
    project_budget = Budget(max_calls=1, scope="project")
    iteration_budget = Budget(max_calls=5, scope="iteration", parent=project_budget)
    operation_budget = Budget(max_calls=5, parent=iteration_budget)
    operation_budget.reserve(calls=1, context_units=20)
    with pytest.raises(BudgetExceeded, match="project calls"):
        operation_budget.reserve(calls=1, context_units=10)
    assert operation_budget.calls == iteration_budget.calls == project_budget.calls == 1
    assert operation_budget.context_units == 20


def test_unknown_live_cost_is_null_and_hard_monetary_cap_prevents_call():
    class Answer(BaseModel):
        answer: str

    calls = []
    provider = CallableProvider("configured-live", lambda request: calls.append(request) or
                                ProviderResponse({"answer": "value"}))
    telemetry = Telemetry()
    assert structured_generate(provider, {}, Answer, telemetry=telemetry).answer == "value"
    assert telemetry.prompt_tokens is None
    assert telemetry.completion_tokens is None
    assert telemetry.estimated_api_cost_usd is None
    with pytest.raises(BudgetExceeded, match="cost is unknown"):
        structured_generate(provider, {}, Answer, budget=Budget(max_cost_usd=1))
    assert len(calls) == 1


def test_provider_output_size_is_bounded_and_unknown_usage_stays_unknown():
    class Answer(BaseModel):
        answer: str

    telemetry = Telemetry()
    provider = CallableProvider("unknown-then-known", lambda request: ProviderResponse(
        {"answer": "value"}, prompt_tokens=3, completion_tokens=2, cost_usd=.1))
    unknown = CallableProvider("unknown-then-known", lambda request: ProviderResponse({"answer": "value"}))
    structured_generate(unknown, {}, Answer, telemetry=telemetry)
    structured_generate(provider, {}, Answer, telemetry=telemetry)
    assert telemetry.prompt_tokens is telemetry.completion_tokens is telemetry.estimated_api_cost_usd is None
    with pytest.raises(ProviderOutputError, match="exceeds"):
        structured_generate(provider, {}, Answer, max_response_units=1, max_retries=0)
