"""Structured merge must preserve data, provenance and explicit conflicts."""

from copy import deepcopy

import pytest

from narrative.core.merge import merge_documents


def document(*nodes, edges=(), **fields):
    return {"title": "Story", "version": "working", "nodes": list(nodes), "edges": list(edges), **fields}


def node(node_id="A", version=1, **fields):
    return {"id": node_id, "kind": "Scene", "label": node_id, "version": version, **fields}


def test_disjoint_node_fields_merge_without_input_mutation_and_bump_version():
    base = document(node(attributes={"theme": "truth", "tension": 1}))
    ours, theirs = deepcopy(base), deepcopy(base)
    ours["nodes"][0].update(label="A choice", version=2)
    theirs["nodes"][0]["attributes"]["tension"] = 3
    theirs["nodes"][0]["version"] = 4
    before = deepcopy((base, ours, theirs))
    result = merge_documents(base, ours, theirs)
    merged = result["document"]["nodes"][0]
    assert result["conflicts"] == []
    assert merged["label"] == "A choice"
    assert merged["attributes"] == {"theme": "truth", "tension": 3}
    assert merged["version"] == 5
    assert "version" not in result["document"]
    assert (base, ours, theirs) == before
    merged["attributes"]["theme"] = "edited result"
    assert base["nodes"][0]["attributes"]["theme"] == "truth"


def test_single_side_edit_keeps_selected_version_and_unchanged_records():
    base = document(node(), node("B", version=7))
    ours, theirs = deepcopy(base), deepcopy(base)
    theirs["nodes"][0].update(label="Changed", version=3)
    ours["version"] = "another commit"
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == []
    assert [record["version"] for record in result["document"]["nodes"]] == [3, 7]


def test_counter_only_changes_never_create_conflicts_or_regress():
    base = document(node(version=1))
    ours, theirs = document(node(version=3)), document(node(version=5))
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == []
    assert result["document"]["nodes"][0]["version"] == 5


def test_selected_record_counter_cannot_regress_below_known_base():
    base = document(node(version=7))
    ours = deepcopy(base)
    theirs = document(node(label="Imported edit", version=1))
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == []
    assert result["document"]["nodes"][0]["label"] == "Imported edit"
    assert result["document"]["nodes"][0]["version"] == 7


def test_equal_semantic_changes_do_not_count_as_composite_edit():
    base = document(node())
    ours = document(node(label="Shared", version=2))
    theirs = document(node(label="Shared", version=3))
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == []
    assert result["document"]["nodes"][0]["version"] == 3


def test_ordered_lists_are_atomic_and_conflicts_preserve_the_original_values():
    base = document(node(threads=["A", "B"]))
    ours = document(node(threads=["A", "B", "C"], version=2))
    theirs = document(node(threads=["B", "A"], version=2))
    result = merge_documents(base, ours, theirs)
    assert result["document"]["nodes"][0]["threads"] == ["A", "B", "C"]
    assert result["conflicts"] == [{"path": "/nodes/A/threads", "reason": "ordered_list_changes", "base": ["A", "B"], "base_exists": True, "ours": ["A", "B", "C"], "ours_exists": True, "theirs": ["B", "A"], "theirs_exists": True}]
    resolved = merge_documents(base, ours, theirs, {"/nodes/A/threads": "theirs"})
    assert resolved["conflicts"] == []
    assert resolved["document"]["nodes"][0]["threads"] == ["B", "A"]


def test_missing_and_null_have_independent_existence_flags():
    base = document(node(attributes={"secret": "unknown"}))
    ours = document(node(attributes={}, version=2))
    theirs = document(node(attributes={"secret": None}, version=2))
    result = merge_documents(base, ours, theirs)
    conflict = result["conflicts"][0]
    assert conflict["path"] == "/nodes/A/attributes/secret"
    assert conflict["ours"] is None and conflict["ours_exists"] is False
    assert conflict["theirs"] is None and conflict["theirs_exists"] is True
    assert "secret" not in result["document"]["nodes"][0]["attributes"]
    resolved = merge_documents(base, ours, theirs, {conflict["path"]: "theirs"})
    assert resolved["document"]["nodes"][0]["attributes"]["secret"] is None


@pytest.mark.parametrize("choice,expected", [("ours", []), ("theirs", ["Changed"]), ("base", ["A"])])
def test_resolving_delete_modify_at_record_root_preserves_deletion(choice, expected):
    base = document(node())
    ours = document()
    theirs = document(node(label="Changed", version=2))
    unresolved = merge_documents(base, ours, theirs)
    assert unresolved["conflicts"][0]["path"] == "/nodes/A"
    assert unresolved["conflicts"][0]["ours_exists"] is False
    result = merge_documents(base, ours, theirs, {"/nodes/A": choice})
    assert result["conflicts"] == []
    assert [record["label"] for record in result["document"]["nodes"]] == expected


def test_unchanged_counter_only_record_does_not_block_other_side_deletion():
    base = document(node())
    ours = document(node(version=3))
    theirs = document()
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == [] and result["document"]["nodes"] == []


def test_independent_additions_sort_records_and_colliding_ids_require_resolution():
    base = document()
    ours = document(node("Z"), node("A", label="Our new node"))
    theirs = document(node("B"), node("A", label="Their new node"))
    unresolved = merge_documents(base, ours, theirs)
    assert [record["id"] for record in unresolved["document"]["nodes"]] == ["A", "B", "Z"]
    assert unresolved["conflicts"][0]["reason"] == "add_add"
    assert unresolved["conflicts"][0]["base_exists"] is False
    resolved = merge_documents(base, ours, theirs, {"/nodes/A": "base"})
    assert [record["id"] for record in resolved["document"]["nodes"]] == ["B", "Z"]


def test_partial_resolutions_do_not_erase_other_conflicts_or_disjoint_edits():
    base = document(node(attributes={"x": 0, "y": 0, "z": 0}))
    ours = document(node(attributes={"x": 1, "y": 1, "z": 0}, version=2))
    theirs = document(node(attributes={"x": 2, "y": 2, "z": 9}, version=2))
    result = merge_documents(base, ours, theirs, {"/nodes/A/attributes/x": "base"})
    assert [item["path"] for item in result["conflicts"]] == ["/nodes/A/attributes/y"]
    assert result["document"]["nodes"][0]["attributes"] == {"x": 0, "y": 1, "z": 9}
    assert result["document"]["nodes"][0]["version"] == 3


def test_json_pointer_escapes_record_ids_and_nested_keys():
    base = document(node("scene/A~B", attributes={"a/b~c": 0}))
    ours = document(node("scene/A~B", attributes={"a/b~c": 1}))
    theirs = document(node("scene/A~B", attributes={"a/b~c": 2}))
    pointer = "/nodes/scene~1A~0B/attributes/a~1b~0c"
    assert merge_documents(base, ours, theirs)["conflicts"][0]["path"] == pointer
    assert merge_documents(base, ours, theirs, {pointer: "theirs"})["document"]["nodes"][0]["attributes"]["a/b~c"] == 2


def test_project_fields_and_edge_records_follow_same_three_way_contract():
    edge = {"id": "cause", "source": "A", "target": "B", "kind": "CAUSES", "weight": 1, "confidence": 1, "version": 1}
    base = document(node(), node("B"), edges=[edge], metadata={"author": "one"})
    ours, theirs = deepcopy(base), deepcopy(base)
    ours["edges"][0].update(weight=2, version=2)
    theirs["edges"][0].update(confidence=0.5, version=4)
    ours["metadata"]["first_reader"] = "reader-a"
    theirs["metadata"]["expert"] = "reader-b"
    result = merge_documents(base, ours, theirs)
    assert result["conflicts"] == []
    assert result["document"]["edges"][0] == {**edge, "weight": 2, "confidence": 0.5, "version": 5}
    assert result["document"]["metadata"] == {"author": "one", "first_reader": "reader-a", "expert": "reader-b"}


def test_revert_delta_preserves_later_unrelated_edit():
    before = document(node(attributes={"theme": "care", "tension": 1}))
    committed = document(node(attributes={"theme": "control", "tension": 1}, version=2))
    current = document(node(attributes={"theme": "control", "tension": 5}, version=3))
    result = merge_documents(committed, current, before)
    assert result["conflicts"] == []
    assert result["document"]["nodes"][0]["attributes"] == {"theme": "care", "tension": 5}
    assert result["document"]["nodes"][0]["version"] == 4


def test_unknown_resolution_paths_and_choices_are_rejected():
    base, ours, theirs = document(), document(), document()
    with pytest.raises(ValueError, match="unknown conflict"):
        merge_documents(base, ours, theirs, {"/nodes/unknown": "ours"})
    with pytest.raises(ValueError, match="choices"):
        merge_documents(base, ours, theirs, {"/title": "blend"})


def test_json_boolean_and_integer_are_not_conflated():
    base = document(metadata={"value": None})
    ours = document(metadata={"value": True})
    theirs = document(metadata={"value": 1})
    assert merge_documents(base, ours, theirs)["conflicts"][0]["path"] == "/metadata/value"


@pytest.mark.parametrize("bad", [document(node(), node()), {"title": "bad", "nodes": {}}, document(node(version=True)), document(metadata={"value": float("nan")})])
def test_malformed_json_records_fail_without_silent_data_loss(bad):
    with pytest.raises(ValueError):
        merge_documents(document(), bad, document())
