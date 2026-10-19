import sqlite3

import pytest
from pydantic import ValidationError

from narrative.core.graph import GraphError, StoryGraph
from narrative.core.schema import (
    Constraint, Edge, Node, Project, State, Transition,
)
from narrative.core.state_machine import simulate
from narrative.core.versioning import SnapshotStore


def story(*nodes, edges=(), state=None, constraints=()):
    return StoryGraph(Project(title="test", nodes=list(nodes), edges=list(edges),
                              initial_state=state or State(), constraints=list(constraints)))


def event(id, time=0, **kwargs):
    return Node(id=id, kind="Event", label=id, time=time, transition=Transition(**kwargs))


def test_schema_rejects_unknown_types_duplicate_ids_and_extra_instructions():
    with pytest.raises(ValidationError):
        Node(id="x", kind="Executable", label="bad")
    with pytest.raises(ValidationError):
        Project(title="bad", nodes=[event("x"), event("x")])
    with pytest.raises(ValidationError):
        Node(id="x", kind="Scene", label="x", execute="rm")


def test_missing_references_and_cycles_detected_but_thematic_contradiction_allowed():
    graph = story(Node(id="a", kind="Scene", label="a", parent_id="b", level=1),
                  Node(id="b", kind="Act", label="b", parent_id="a", level=2),
                  edges=[Edge(id="e", source="a", target="missing", kind="CAUSES")])
    assert {f.code for f in graph.validate()} >= {"DANGLING_EDGE", "HIERARCHY_CYCLE"}
    valid = story(event("a"), event("b"), edges=[Edge(id="e", source="a", target="b", kind="CONTRADICTS")])
    assert valid.validate() == []


def test_failed_event_is_atomic_and_later_events_observe_original_state():
    graph = story(event("failed", time=1, requires={"resource.key": True}, effects={"world.door": "open"},
                        knowledge_updates={"a": ["secret"]}),
                  event("later", time=2, requires={"world.door": "closed"}, effects={"world.safe": True}),
                  state=State(values={"world.door": "closed"}))
    result = simulate(graph)
    assert result.applied == ["later"]
    assert result.state.values["world.door"] == "closed"
    assert result.state.knowledge == {}
    assert result.findings[0].code == "PRECONDITION"


def test_belief_is_not_knowledge_and_audience_is_separate():
    graph = story(event("choice", requires_knowledge={"a": ["secret"]}),
                  state=State(knowledge={"audience": ["secret"]}, beliefs={"a": ["secret"]}))
    assert simulate(graph).findings[0].code == "UNKNOWN_SECRET"


def test_chronology_independent_from_presentation_order_and_proposals_ignored():
    reveal = event("reveal", time=1, knowledge_updates={"a": ["secret"]})
    reveal.order = 20
    choice = event("choice", time=2, requires_knowledge={"a": ["secret"]})
    choice.order = 1
    proposed = event("proposal", time=0, effects={"world.impossible": True})
    proposed.status = "PROPOSED"
    result = simulate(story(choice, reveal, proposed))
    assert result.applied == ["reveal", "choice"]
    assert not result.findings
    assert "world.impossible" not in result.state.values


def test_irreversible_effect_requires_canonical_established_rule():
    loss = event("loss", time=1, effects={"character.a.voice": False}, irreversible=["character.a.voice"])
    restore = event("restore", time=2, effects={"character.a.voice": True}, exceptions=["repair"])
    graph = story(loss, restore)
    assert simulate(graph).findings[0].code == "IRREVERSIBLE"
    graph.add_node(Node(id="repair", kind="Rule", label="repair", attributes={"exception_for": "character.a.voice"}))
    assert simulate(graph).findings == []
    graph.update_node("repair", {"status": "HYPOTHETICAL"})
    assert simulate(graph).findings[0].code == "IRREVERSIBLE"


def test_invariants_checked_at_initial_and_each_atomic_transition():
    constraint = Constraint(id="physics", key="world.speed", expected=1)
    graph = story(event("break", effects={"world.speed": 2}),
                  state=State(values={"world.speed": 1}), constraints=[constraint])
    result = simulate(graph)
    assert result.findings[0].code == "INVARIANT"
    assert result.state.values["world.speed"] == 1


def test_defensive_graph_access_and_branch_changes_preserve_original():
    graph = story(event("a"))
    graph.nodes["a"].label = "oops"
    graph.document.nodes[0].label = "oops"
    branch = graph.clone()
    branch.update_node("a", {"label": "branch"})
    assert graph.get("a").label == "a"
    assert branch.get("a").version == 2


def test_locked_change_and_proposal_promotion_require_explicit_authorization():
    graph = story(Node(id="a", kind="Rule", label="a", locked=True),
                  Node(id="p", kind="Scene", label="p", status="PROPOSED"))
    with pytest.raises(GraphError, match="Locked"):
        graph.update_node("a", {"label": "new"})
    with pytest.raises(GraphError, match="Promoting"):
        graph.update_node("p", {"status": "CANON"})
    graph.update_node("a", {"label": "new"}, authorized=True)
    graph.update_node("p", {"status": "CANON"}, authorized=True)
    assert graph.get("p").status == "CANON"


def test_immutable_sqlite_reload_diff_and_commit_guard(tmp_path):
    store = SnapshotStore(tmp_path / "story.db")
    graph = story(Node(id="a", kind="Rule", label="a", locked=True))
    first = store.commit(graph, message="initial")
    modified = graph.clone()
    modified.update_node("a", {"label": "changed"}, authorized=True)
    with pytest.raises(GraphError, match="authorization"):
        store.commit(modified, parent=first)
    second = store.commit(modified, parent=first, authorized_locked=["a"])
    assert store.load(first).get("a").label == "a"
    assert store.load().get("a").label == "changed"
    assert store.diff(first, second)["nodes"]["changed"] == ["a"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.connection.execute("UPDATE snapshots SET document='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="append only"):
        store.connection.execute("DELETE FROM history")
    store.close()


def test_unknown_parent_snapshot_fails_and_invalid_import_not_committed(tmp_path):
    store = SnapshotStore(tmp_path / "story.db")
    with pytest.raises(GraphError, match="Unknown snapshot"):
        store.commit(story(event("a")), parent="missing")
    invalid = story(Node(id="a", kind="Scene", label="a", parent_id="missing"))
    with pytest.raises(GraphError, match="Invalid graph"):
        store.commit(invalid)
    assert store.history() == []
    store.close()


def test_omitting_parent_does_not_bypass_locked_snapshot_guard(tmp_path):
    store = SnapshotStore(tmp_path / "story.db")
    graph = story(Node(id="a", kind="Rule", label="a", locked=True))
    store.commit(graph)
    changed = graph.clone()
    changed.update_node("a", {"label": "bypass"}, authorized=True)
    with pytest.raises(GraphError, match="authorization"):
        store.commit(changed)
    store.close()


def test_ancestor_invariants_constrain_canonical_descendant_events():
    parent = Node(id="act", kind="Act", label="act", level=1,
                  hard_constraints=[Constraint(id="truth", key="world.truth", expected=True)])
    child = event("child", effects={"world.truth": False})
    child.parent_id = "act"
    child.level = 2
    graph = story(parent, child, state=State(values={"world.truth": True}))
    result = simulate(graph)
    assert result.applied == []
    assert result.state.values["world.truth"] is True
    assert result.findings[0].code == "LOCAL_INVARIANT"


def test_hypothesis_cannot_execute_as_actual_canon_and_timeline_must_be_finite():
    graph = story(Node(id="h", kind="Hypothesis", label="uncertain", transition=Transition(effects={"world.claim": True})))
    assert simulate(graph).applied == []
    assert "HYPOTHESIS_TRANSITION" in {f.code for f in graph.validate()}
    with pytest.raises(ValidationError):
        Node(id="bad", kind="Scene", label="bad", time=float("nan"))


def test_inherited_design_commitment_conflict_detected_without_redundant_annotations():
    parent = Node(id="act", kind="Act", label="act", level=1,
                  hard_constraints=[Constraint(id="theme", key="theme", expected="care", scope="design")],
                  attributes={"theme": "care"})
    child = Node(id="child", kind="Scene", label="child", parent_id="act", level=2)
    graph = story(parent, child)
    assert graph.validate() == []
    graph.update_node("child", {"attributes": {"theme": "abandonment"}})
    assert "DESIGN_CONSTRAINT" in {f.code for f in graph.validate()}
