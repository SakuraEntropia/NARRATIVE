"""Independent regressions for immutable revision identity and stale aliases."""

import pytest

from narrative.core.graph import GraphError, StoryGraph
from narrative.core.schema import Node, Project
from narrative.core.versioning import SnapshotStore


def _story(label="Original"):
    return StoryGraph(Project(title="Review", nodes=[Node(id="scene", kind="Scene", label=label)]))


def _changed(graph, label):
    branch = graph.clone()
    branch.update_node("scene", {"label": label})
    return branch


def test_full_commit_identity_cannot_be_shadowed_by_a_moving_reference(tmp_path):
    store = SnapshotStore(tmp_path / "hash-name.db")
    try:
        original = store.commit(_story(), message="Immutable original")
        try:
            store.create_branch(original)
        except (GraphError, ValueError):
            # Reserving hash-shaped names also prevents the ambiguity.
            return
        store.checkout("refs/heads/" + original)
        moved = store.commit(_changed(store.load(), "Moved reference content"))
        assert moved != original
        assert store.resolve(original) == original
        assert store.load(original).get("scene").label == "Original"
        assert store.show(original)["id"] == original
    finally:
        store.close()


@pytest.mark.parametrize("operation", ["commit", "save_working"])
def test_old_snapshot_alias_cannot_bypass_stale_graph_protection(tmp_path, operation):
    store = SnapshotStore(tmp_path / f"stale-alias-{operation}.db")
    try:
        original = store.commit(_story(), message="Original")
        old_alias = store.show(original)["snapshot"]
        current = store.commit(_changed(store.load(), "Current"), message="Current")
        stale = _changed(store.load(old_alias), "Replacement from stale content alias")
        before = store.status()
        with pytest.raises((GraphError, ValueError), match="[Ss]tale|alias|ancestry|HEAD|parent"):
            getattr(store, operation)(stale)
        assert store.status() == before
        assert store.status()["head"] == current
        assert store.load().get("scene").label == "Current"
        assert len(store.history()) == 2
    finally:
        store.close()


def test_refreshing_store_token_does_not_make_an_old_graph_current(tmp_path):
    path = tmp_path / "refreshed-token.db"
    first = SnapshotStore(path)
    second = None
    try:
        original = first.commit(_story())
        captured_before_draft = first.load()
        second = SnapshotStore(path)
        second.save_working(_changed(second.load(), "New draft to preserve"))
        # A read refreshes the connection's observed revision, but cannot make a
        # previously captured clean graph represent the newly saved draft.
        assert first.load().get("scene").label == "New draft to preserve"
        before = first.status()
        with pytest.raises((GraphError, ValueError), match="[Ss]tale|working|draft|revision"):
            first.save_working(_changed(captured_before_draft, "Stale replacement"))
        assert first.status() == before
        assert first.status()["head"] == original
        assert first.load().get("scene").label == "New draft to preserve"
    finally:
        first.close()
        if second:
            second.close()


def test_observed_status_guards_discard_checkout_against_unseen_drafts(tmp_path):
    path = tmp_path / "observed-status.db"
    writer = SnapshotStore(path)
    observer = None
    try:
        original = writer.commit(_story())
        observer = SnapshotStore(path)
        assert observer.status()["dirty"] is False
        writer.save_working(_changed(writer.load(), "Unseen concurrent draft"))
        with pytest.raises((GraphError, ValueError), match="[Ss]tale|[Cc]oncurrent|revision|HEAD"):
            observer.checkout("main", discard_changes=True)
        assert writer.status()["head"] == original
        assert writer.load().get("scene").label == "Unseen concurrent draft"
        assert writer.status()["dirty"] is True
    finally:
        writer.close()
        if observer:
            observer.close()
