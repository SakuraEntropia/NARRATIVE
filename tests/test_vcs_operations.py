"""Canon protection and recoverability across merge and inverse changes."""

import pytest
import json

from narrative.cli import main
from narrative.core.graph import GraphError, StoryGraph
from narrative.core.schema import Node, Project
from narrative.core.versioning import SnapshotStore


@pytest.fixture
def store(tmp_path):
    result = SnapshotStore(tmp_path / "operation.db")
    yield result
    result.close()


def initial(store, **kwargs):
    return store.commit(StoryGraph(Project(title="Protected revision", nodes=[
        Node(id="scene", kind="Scene", label="Opening", **kwargs),
    ])), message="Initial")


def change(store, label, *, authorized=False):
    graph = store.load()
    graph.update_node("scene", {"label": label}, authorized=authorized)
    return store.commit(graph, message=label, authorized_locked=["scene"] if authorized else [])


def test_fast_forward_cannot_overwrite_locked_canon_without_authorization(store):
    first = initial(store, locked=True)
    store.create_branch("alternative")
    store.checkout("alternative")
    alternative = change(store, "Different locked fact", authorized=True)
    store.checkout("main")
    with pytest.raises(GraphError, match="Locked"):
        store.merge("alternative")
    assert store.status()["head"] == first
    assert store.status()["pending"] is None
    assert len(store.history()) == 2
    assert store.merge("alternative", authorized_locked=["scene"])["status"] == "fast_forward"
    assert store.status()["head"] == alternative


def test_fast_forward_promotion_requires_node_specific_approval(store):
    first = initial(store, status="PROPOSED")
    store.create_branch("approved")
    store.checkout("approved")
    proposal = store.load()
    proposal.update_node("scene", {"status": "CANON"}, authorized=True)
    store.commit(proposal, authorized_locked=["scene"])
    store.checkout("main")
    with pytest.raises(GraphError, match="promotion"):
        store.merge("approved", authorized_locked=["unrelated"])
    assert store.status()["head"] == first
    assert store.merge("approved", authorized_locked=["scene"])["committed"]
    assert store.load().get("scene").status == "CANON"


def test_merge_resolution_renews_locked_permission_at_final_commit(store):
    initial(store, locked=True)
    store.create_branch("alternative")
    main = change(store, "Main fact", authorized=True)
    store.checkout("alternative")
    alternative = change(store, "Other fact", authorized=True)
    store.checkout("main")
    with pytest.raises(GraphError, match="Locked"):
        store.merge("alternative")
    conflict = store.merge("alternative", authorized_locked=["scene"])
    assert conflict["status"] == "conflicts"
    path = conflict["conflicts"][0]["path"]
    store.resolve_conflicts({path: "theirs"})
    with pytest.raises(GraphError, match="Locked"):
        store.commit_working("Forgot renewed permission")
    assert store.status()["head"] == main
    merged = store.commit_working("Choose other fact", authorized_locked=["scene"])
    assert store.show(merged)["parents"] == [main, alternative]
    assert store.load().get("scene").label == "Other fact"


def test_conflicting_revert_preserves_later_annotations_and_has_one_parent(store):
    initial(store)
    selected = change(store, "First change")
    current = store.load()
    current.update_node("scene", {"label": "Later change", "attributes": {"retain": True}})
    current_id = store.commit(current, message="Later independent annotation")
    result = store.revert(selected)
    assert result["status"] == "conflicts"
    assert store.status()["head"] == current_id
    assert store.status()["pending"]["kind"] == "revert"
    with pytest.raises(GraphError, match="Unresolved"):
        store.commit_working("Cannot commit unresolved revert")
    path = result["conflicts"][0]["path"]
    store.resolve_conflicts({path: "theirs"})
    reverted = store.commit_working("Undo first change by explicit conflict choice")
    assert store.show(reverted)["parents"] == [current_id]
    assert store.show(reverted)["metadata"]["source"] == selected
    assert store.load().get("scene").label == "Opening"
    assert store.load().get("scene").attributes == {"retain": True}


def test_pending_operation_blocks_other_mutations_and_abort_is_exact(store):
    initial(store)
    store.create_branch("alternative")
    main = change(store, "Main")
    store.checkout("alternative")
    change(store, "Alternative")
    store.checkout("main")
    before = store.load().document.model_dump(mode="json")
    conflict = store.merge("alternative")
    assert conflict["status"] == "conflicts"
    for operation in (lambda: store.checkout("main", discard_changes=True),
                      lambda: store.commit(store.load(), message="Bypass"),
                      lambda: store.save_working(store.load()),
                      lambda: store.merge("alternative"), lambda: store.revert(main)):
        with pytest.raises(GraphError, match="Pending"):
            operation()
    assert store.status()["head"] == main
    assert store.abort_merge()["status"] == "aborted"
    assert store.load().document.model_dump(mode="json") == before
    with pytest.raises(GraphError, match="No pending"):
        store.abort_merge()


def test_reflog_records_checkout_and_fast_forward_for_detached_recovery(store):
    first = initial(store)
    store.create_branch("alternative")
    store.checkout("alternative")
    other = change(store, "Other")
    store.checkout("main")
    store.merge("alternative")
    entries = store.reflog(limit=3)
    assert [entry["action"] for entry in entries] == ["fast_forward", "checkout", "commit"]
    assert entries[0]["old_head"] == first
    assert entries[0]["new_head"] == other
    assert entries[1]["detail"]["revision"] == "main"
    with pytest.raises(GraphError, match="limit"):
        store.reflog(limit=0)


def test_cli_commit_author_and_operation_history_are_inspectable(store, capsys):
    initial(store)
    graph = store.load()
    graph.update_node("scene", {"label": "Saved draft"})
    store.save_working(graph)
    assert main(["--db", str(store.path), "commit", "-m", "Record choice", "--author", "Mara"]) == 0
    committed = json.loads(capsys.readouterr().out)["version"]
    assert store.show(committed)["author"] == "Mara"
    assert main(["--db", str(store.path), "reflog", "--limit", "1"]) == 0
    entry = json.loads(capsys.readouterr().out)["reflog"][0]
    assert entry["action"] == "commit" and entry["new_head"] == committed
    assert main(["--db", str(store.path), "reflog", "--limit", "0"]) == 2
    assert "limit" in json.loads(capsys.readouterr().out)["message"]
