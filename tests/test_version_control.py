"""Black-box regression coverage for persistent, Git-inspired story histories."""

import hashlib
import json
import sqlite3

import pytest

from narrative.core.graph import GraphError, StoryGraph
from narrative.core.schema import Node, Project, State, Transition
from narrative.core.state_machine import simulate
from narrative.core.versioning import SnapshotStore


def story(label="Original", *, locked=False, status="CANON"):
    return StoryGraph(Project(title="Branching archive", nodes=[
        Node(id="scene", kind="Scene", label=label, locked=locked, status=status),
    ]))


def changed(graph, label):
    branch = graph.clone()
    branch.update_node("scene", {"label": label}, authorized=True)
    return branch


@pytest.fixture
def store(tmp_path):
    result = SnapshotStore(tmp_path / "story.db")
    try:
        yield result
    finally:
        result.close()


def commit_label(store, label, message=None):
    graph = changed(store.load(), label)
    return store.commit(graph, message=message or label)


def ref_map(refs):
    return {item["name"]: item["target"] for item in refs}


def test_duplicate_story_blobs_have_distinct_commit_identity_and_parent_chain(store):
    first = store.commit(story(), message="First interpretation")
    second = store.commit(store.load(), message="Same text, a separate author decision")
    assert first != second
    assert store.show(first)["snapshot"] == store.show(second)["snapshot"]
    assert store.show(first)["parents"] == []
    assert store.show(second)["parents"] == [first]
    assert store.status()["head"] == second
    assert store.load(first).get("scene").label == "Original"
    assert store.load(second).get("scene").label == "Original"
    assert [entry["version"] for entry in store.history()] == [first, second]


def test_persistent_working_copy_is_separate_from_immutable_head(tmp_path):
    path = tmp_path / "persistent.db"
    store = SnapshotStore(path)
    first = store.commit(story(), message="Initial")
    original = store.load()
    draft = changed(original, "Uncommitted detail")
    store.save_working(draft)
    status = store.status()
    assert status["branch"] == "main"
    assert status["head"] == first
    assert status["dirty"] is True
    assert status["changes"]["nodes"]["changed"] == ["scene"]
    assert store.load().document.version.startswith("working:")
    assert store.load(first).get("scene").label == "Original"
    assert original.get("scene").label == "Original"
    store.close()
    reopened = SnapshotStore(path)
    try:
        assert reopened.status()["dirty"] is True
        assert reopened.load().get("scene").label == "Uncommitted detail"
        second = reopened.commit_working("Record the detail", author="Mara")
        assert reopened.show(second)["author"] == "Mara"
        assert reopened.show(second)["parents"] == [first]
        assert reopened.status()["dirty"] is False
        assert reopened.load(first).get("scene").label == "Original"
    finally:
        reopened.close()


def test_branch_and_tag_creation_do_not_switch_and_names_cannot_be_replaced(store):
    first = store.commit(story(), message="Start")
    assert store.create_branch("alternate") == {"name": "alternate", "target": first}
    assert store.create_tag("opening") == {"name": "opening", "target": first}
    assert store.status()["branch"] == "main"
    assert store.status()["head"] == first
    assert ref_map(store.branches()) == {"main": first, "alternate": first}
    assert ref_map(store.tags()) == {"opening": first}
    with pytest.raises((GraphError, ValueError)):
        store.create_branch("alternate")
    with pytest.raises((GraphError, ValueError)):
        store.create_tag("opening")


def test_dirty_checkout_preserves_work_and_explicit_discard_restores_branch(store):
    first = store.commit(story(), message="Start")
    store.create_branch("alternate")
    store.save_working(changed(store.load(), "Unsaved alternative"))
    revision = store.status()["revision"]
    with pytest.raises((GraphError, ValueError), match="[Dd]irty|uncommitted|working"):
        store.checkout("alternate")
    assert store.status()["head"] == first
    assert store.status()["revision"] == revision
    assert store.load().get("scene").label == "Unsaved alternative"
    store.checkout("alternate", discard_changes=True)
    assert store.status()["branch"] == "alternate"
    assert store.status()["dirty"] is False
    assert store.load().get("scene").label == "Original"


def test_branch_isolation_tags_and_detached_head_commits(store):
    initial = store.commit(story(), message="Start")
    store.create_branch("alternate")
    store.create_tag("opening")
    store.checkout("alternate")
    alternate = commit_label(store, "Alternate ending")
    store.checkout("main")
    assert store.load().get("scene").label == "Original"
    assert ref_map(store.branches())["alternate"] == alternate
    store.checkout("opening")
    assert store.status()["detached"] is True
    assert store.status()["branch"] is None
    detached = commit_label(store, "Detached experiment")
    assert store.status()["head"] == detached
    assert store.status()["detached"] is True
    assert store.show(detached)["parents"] == [initial]
    assert ref_map(store.branches()) == {"main": initial, "alternate": alternate}
    assert ref_map(store.tags())["opening"] == initial
    store.checkout("main")
    assert store.status()["detached"] is False


def test_revision_selectors_prefixes_show_and_log_are_commit_based(store):
    first = store.commit(story(), message="First")
    second = commit_label(store, "Second")
    third = commit_label(store, "Third")
    assert store.resolve("HEAD") == third
    assert store.resolve("HEAD~0") == third
    assert store.resolve("HEAD~1") == second
    assert store.resolve("HEAD~2") == first
    assert store.resolve("HEAD^1") == second
    assert store.resolve(third[:12]) == third
    assert store.resolve("main") == third
    with pytest.raises((GraphError, ValueError)):
        store.resolve("HEAD~3")
    with pytest.raises((GraphError, ValueError)):
        store.resolve("HEAD^2")
    with pytest.raises((GraphError, ValueError)):
        store.resolve(third[:6])
    entry = store.show(second)
    assert entry["id"] == entry["version"] == second
    assert entry["message"] == "Second"
    assert entry["parents"] == [first]
    assert entry["document"]["nodes"][0]["label"] == "Second"
    assert entry["created"] and isinstance(entry["metadata"], dict)
    assert [entry["id"] for entry in store.log(limit=2)] == [third, second]


def test_explicit_stale_parent_cannot_rewind_active_branch(store):
    first = store.commit(story(), message="First")
    stale = store.load()
    second = commit_label(store, "Second")
    count = len(store.history())
    with pytest.raises((GraphError, ValueError), match="[Ss]tale|HEAD|parent|[Cc]oncurrent"):
        store.commit(changed(stale, "Stale replacement"), parent=first)
    assert store.status()["head"] == second
    assert len(store.history()) == count
    assert store.load().get("scene").label == "Second"


def test_two_connections_reject_stale_automatic_commit_without_lost_history(tmp_path):
    path = tmp_path / "concurrent.db"
    first = SnapshotStore(path)
    first.commit(story(), message="Start")
    second = SnapshotStore(path)
    try:
        first_work = first.load()
        second_work = second.load()
        winner = first.commit(changed(first_work, "Winner"), message="Winner")
        with pytest.raises((GraphError, ValueError), match="[Ss]tale|[Cc]oncurrent|revision|HEAD"):
            second.commit(changed(second_work, "Stale writer"), message="Must not appear")
        assert first.status()["head"] == winner
        assert first.load().get("scene").label == "Winner"
        assert len(first.history()) == 2
        assert all(item["message"] != "Must not appear" for item in first.log(all_branches=True))
        second.close()
        second = SnapshotStore(path)
        second_work = second.load()
        next_commit = second.commit(changed(second_work, "Fresh writer"), message="Fresh writer")
        assert second.show(next_commit)["parents"] == [winner]
    finally:
        first.close()
        second.close()


def test_two_connections_reject_stale_working_save_without_overwriting_draft(tmp_path):
    path = tmp_path / "drafts.db"
    first = SnapshotStore(path)
    first.commit(story(), message="Start")
    second = SnapshotStore(path)
    try:
        first_work, second_work = first.load(), second.load()
        first.save_working(changed(first_work, "Preserved draft"))
        with pytest.raises((GraphError, ValueError), match="[Ss]tale|[Cc]oncurrent|revision|HEAD"):
            second.save_working(changed(second_work, "Lost draft"))
        assert first.load().get("scene").label == "Preserved draft"
        assert first.status()["dirty"] is True
        assert len(first.history()) == 1
    finally:
        first.close()
        second.close()


def test_locked_nodes_and_canon_promotion_are_rechecked_at_save_and_commit(store):
    initial = store.commit(story(locked=True), message="Locked baseline")
    draft = changed(store.load(), "Authorized edit")
    with pytest.raises((GraphError, ValueError), match="[Ll]ock|authorization"):
        store.save_working(draft)
    store.save_working(draft, authorized_locked=["scene"])
    with pytest.raises((GraphError, ValueError), match="[Ll]ock|authorization"):
        store.commit_working("Missing renewed authorization")
    assert store.status()["head"] == initial
    committed = store.commit_working("Authorized commit", authorized_locked=["scene"])
    assert store.load(committed).get("scene").label == "Authorized edit"


def test_promotion_in_prebuilt_graph_cannot_bypass_snapshot_authorization(store):
    initial = store.commit(story(status="PROPOSED"), message="Proposal")
    proposal = store.load()
    proposal.update_node("scene", {"status": "CANON"}, authorized=True)
    with pytest.raises((GraphError, ValueError), match="[Pp]romot|[Cc]anon|authorization"):
        store.commit(proposal)
    assert store.status()["head"] == initial
    assert store.status()["dirty"] is False
    with pytest.raises((GraphError, ValueError), match="[Pp]romot|[Cc]anon|authorization"):
        store.save_working(proposal)
    store.save_working(proposal, authorized_locked=["scene"])
    final = store.commit_working("Approve proposal", authorized_locked=["scene"])
    assert store.load(final).get("scene").status == "CANON"


def test_auto_commit_compares_current_head_instead_of_author_supplied_source(store):
    first = store.commit(story(locked=True), message="Locked baseline")
    external = story(label="Replacement without source identity", locked=True)
    with pytest.raises((GraphError, ValueError), match="[Ll]ock|authorization"):
        store.commit(external)
    assert store.status()["head"] == first
    assert store.load().get("scene").label == "Original"


def test_ordinary_commits_can_store_a_story_with_a_state_defect(store):
    defective = StoryGraph(Project(title="Unresolved precondition", nodes=[
        Node(id="open", kind="Event", label="Open door", transition=Transition(
            requires={"resource.key": True}, effects={"world.door": "open"})),
    ]))
    assert any(finding.code == "PRECONDITION" for finding in simulate(defective).findings)
    version = store.commit(defective, message="Record a defect for later revision")
    assert store.status()["head"] == version
    assert store.load(version).get("open").transition.requires == {"resource.key": True}


def legacy_database(path):
    """Write the actual v1 schema without importing the v2 store implementation."""
    documents = {}
    for label in ("A", "B"):
        document = story(label).document.model_dump(mode="json")
        document["version"] = "snapshot"
        encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        documents[label] = (hashlib.sha256(encoded.encode()).hexdigest(), encoded)
    a, b = documents["A"][0], documents["B"][0]
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE snapshots (id TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE TABLE history (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL REFERENCES snapshots(id), parent TEXT, message TEXT NOT NULL,
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TRIGGER snapshots_no_update BEFORE UPDATE ON snapshots
            BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
        CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON snapshots
            BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
        CREATE TRIGGER history_no_update BEFORE UPDATE ON history
            BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
        CREATE TRIGGER history_no_delete BEFORE DELETE ON history
            BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
    """)
    connection.executemany("INSERT INTO snapshots VALUES (?,?)", documents.values())
    entries = [(a, None, "First"), (a, a, "Same content"), (b, a, "Change"),
               (a, b, "Return"), (b, a, "Ambiguous old parent"), (b, b, "Content self-parent")]
    connection.executemany("INSERT INTO history(version,parent,message,created) VALUES (?,?,?,?)",
                           [(version, parent, message, f"2026-10-19 00:00:0{index}")
                            for index, (version, parent, message) in enumerate(entries)])
    connection.commit()
    connection.close()
    return a, b


def legacy_rows(path):
    connection = sqlite3.connect(path)
    try:
        return {
            "snapshots": connection.execute("SELECT * FROM snapshots ORDER BY id").fetchall(),
            "history": connection.execute("SELECT * FROM history ORDER BY sequence").fetchall(),
            "triggers": connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                                           "AND tbl_name IN ('snapshots','history') ORDER BY name").fetchall(),
        }
    finally:
        connection.close()


def test_v1_migration_preserves_raw_rows_and_maps_duplicate_content_events(tmp_path):
    path = tmp_path / "legacy.db"
    a, b = legacy_database(path)
    original_rows = legacy_rows(path)
    store = SnapshotStore(path)
    commits = store.history()
    assert len(commits) == 6
    versions = [entry["version"] for entry in commits]
    assert len(set(versions)) == 6
    assert store.show(versions[0])["parents"] == []
    for index in range(1, 6):
        assert store.show(versions[index])["parents"] == [versions[index - 1]]
    assert store.show(versions[0])["snapshot"] == store.show(versions[1])["snapshot"] == a
    assert store.show(versions[4])["snapshot"] == store.show(versions[5])["snapshot"] == b
    assert any("ambig" in json.dumps(store.show(version)["metadata"]).lower() for version in versions)
    assert store.status()["head"] == versions[-1]
    assert store.load(a).get("scene").label == "A"
    assert store.load(b).get("scene").label == "B"
    with pytest.raises((GraphError, ValueError), match="[Aa]mbig"):
        store.resolve(a)
    store.close()
    assert legacy_rows(path) == original_rows
    reopened = SnapshotStore(path)
    try:
        assert [entry["version"] for entry in reopened.history()] == versions
        assert reopened.status()["head"] == versions[-1]
    finally:
        reopened.close()
    assert legacy_rows(path) == original_rows


def test_commit_records_and_legacy_snapshot_history_remain_immutable(store):
    store.commit(story(), message="Immutable")
    statements = ["UPDATE vcs_commits SET message='rewritten'", "DELETE FROM vcs_commits",
                  "UPDATE snapshots SET document='{}'", "DELETE FROM history"]
    for statement in statements:
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(statement)
        store.connection.rollback()


def diverged_labels(store):
    initial = store.commit(story(), message="Common opening")
    store.create_branch("alternate")
    ours = store.load()
    ours.update_node("scene", {"label": "Main ending", "attributes": {"main_note": "preserve me"}})
    main = store.commit(ours, message="Main ending")
    store.checkout("alternate")
    theirs = store.load()
    theirs.update_node("scene", {"label": "Alternate ending", "attributes": {"alternate_note": "also preserve me"}})
    alternate = store.commit(theirs, message="Alternate ending")
    store.checkout("main")
    return initial, main, alternate


def test_disjoint_changes_merge_to_a_two_parent_commit_without_mutating_sources(store):
    initial = store.commit(story(), message="Opening")
    store.create_branch("alternate")
    main = commit_label(store, "Main ending")
    store.checkout("alternate")
    theirs = store.load()
    theirs.update_node("scene", {"attributes": {"prop": "archive key"}})
    alternate = store.commit(theirs, message="Add a prop")
    store.checkout("main")
    result = store.merge("alternate", message="Combine ending and prop")
    assert result["status"] == "merged"
    assert result["committed"] is True
    merged = store.status()["head"]
    assert store.show(merged)["parents"] == [main, alternate]
    assert store.load().get("scene").label == "Main ending"
    assert store.load().get("scene").attributes == {"prop": "archive key"}
    assert store.load(initial).get("scene").label == "Original"
    assert store.load(main).get("scene").attributes == {}
    assert store.load(alternate).get("scene").label == "Original"
    assert store.resolve("HEAD^1") == main
    assert store.resolve("HEAD^2") == alternate
    assert store.resolve("HEAD~2") == initial
    assert ref_map(store.branches())["alternate"] == alternate


def test_fast_forward_and_up_to_date_do_not_invent_extra_commits(store):
    initial = store.commit(story(), message="Opening")
    store.create_branch("alternate")
    store.checkout("alternate")
    alternate = commit_label(store, "A later scene")
    store.checkout("main")
    assert store.status()["head"] == initial
    result = store.merge("alternate")
    assert result["status"] == "fast_forward" and result["committed"] is True
    assert store.status()["head"] == alternate
    assert len(store.history()) == 2
    result = store.merge("alternate")
    assert result["status"] == "up_to_date" and result["committed"] is False
    assert len(store.history()) == 2


def test_merge_conflicts_persist_and_scoped_resolution_keeps_unrelated_edits(tmp_path):
    path = tmp_path / "conflicts.db"
    store = SnapshotStore(path)
    _, main, alternate = diverged_labels(store)
    result = store.merge("alternate")
    assert result["status"] == "conflicts" and result["committed"] is False
    assert store.status()["head"] == main
    paths = [conflict["path"] for conflict in result["conflicts"]]
    assert len(paths) == 1 and paths[0].endswith("/label")
    for conflict in result["conflicts"]:
        assert {"base", "ours", "theirs", "reason"} <= conflict.keys()
    store.close()
    reopened = SnapshotStore(path)
    try:
        resolved = reopened.resolve_conflicts({paths[0]: "theirs"})
        assert resolved["status"] == "resolved" and resolved["committed"] is False
        assert reopened.status()["head"] == main
        node = reopened.load().get("scene")
        assert node.label == "Alternate ending"
        assert node.attributes == {"main_note": "preserve me", "alternate_note": "also preserve me"}
        merged = reopened.commit_working("Resolve the ending")
        assert reopened.show(merged)["parents"] == [main, alternate]
        assert reopened.status()["dirty"] is False
    finally:
        reopened.close()


def test_abort_restores_exact_pre_merge_work_and_head(store):
    _, main, _ = diverged_labels(store)
    before = store.load().document.model_dump(mode="json")
    history_count = len(store.history())
    assert store.merge("alternate")["status"] == "conflicts"
    result = store.abort_merge()
    assert result["status"] == "aborted" and result["committed"] is False
    assert store.status()["head"] == main
    assert store.load().document.model_dump(mode="json") == before
    assert len(store.history()) == history_count


def test_dirty_work_is_not_discarded_by_merge(store):
    store.commit(story(), message="Opening")
    store.create_branch("alternate")
    store.save_working(changed(store.load(), "Keep this draft"))
    before = store.status()
    with pytest.raises((GraphError, ValueError), match="[Dd]irty|uncommitted|working"):
        store.merge("alternate")
    assert store.status() == before
    assert store.load().get("scene").label == "Keep this draft"


def test_merge_rejects_new_forward_state_regression_and_preserves_sources(store):
    baseline = StoryGraph(Project(title="Two individually coherent branches", nodes=[
        Node(id="provision", kind="Event", label="Provision key", time=1,
             transition=Transition(effects={"resource.key": True})),
    ], initial_state=State(values={"resource.key": False})))
    store.commit(baseline, message="Key available")
    store.create_branch("consumer")
    ours = store.load()
    ours.update_node("provision", {"transition": {"effects": {"resource.key": False}}})
    main = store.commit(ours, message="Key not provisioned")
    assert simulate(store.load()).findings == []
    store.checkout("consumer")
    theirs = store.load()
    theirs.add_node(Node(id="consume", kind="Event", label="Use the key", time=2,
                         transition=Transition(requires={"resource.key": True})))
    consumer = store.commit(theirs, message="Consume available key")
    assert simulate(store.load()).findings == []
    store.checkout("main")
    before = store.load().document.model_dump(mode="json")
    count = len(store.history())
    result = store.merge("consumer")
    assert result["status"] == "invalid" and result["committed"] is False
    assert any(finding["code"] == "PRECONDITION" for finding in result["findings"])
    assert store.status()["head"] == main
    assert store.load().document.model_dump(mode="json") == before
    assert len(store.history()) == count
    assert store.load(consumer).get("consume").transition.requires == {"resource.key": True}


def test_merge_can_preserve_an_existing_baseline_state_defect(store):
    graph = StoryGraph(Project(title="Known missing key", nodes=[
        Node(id="scene", kind="Scene", label="Original"),
        Node(id="known_defect", kind="Event", label="Missing key", transition=Transition(
            requires={"resource.key": True})),
    ]))
    store.commit(graph, message="Record known defect")
    store.create_branch("alternate")
    main = commit_label(store, "Main label")
    store.checkout("alternate")
    alternate_graph = store.load()
    alternate_graph.update_node("scene", {"attributes": {"note": "independent detail"}})
    alternate = store.commit(alternate_graph, message="Independent annotation")
    store.checkout("main")
    result = store.merge("alternate")
    assert result["status"] == "merged" and result["committed"] is True
    assert store.show()["parents"] == [main, alternate]
    assert any(finding.code == "PRECONDITION" for finding in simulate(store.load()).findings)


def test_revert_preserves_later_unrelated_changes_and_makes_a_new_commit(store):
    first = store.commit(story(), message="Opening")
    rename = commit_label(store, "Changed label")
    later = store.load()
    later.update_node("scene", {"attributes": {"later_note": "preserve this"}})
    previous = store.commit(later, message="Later note")
    result = store.revert(rename, message="Undo the label only")
    assert result["committed"] is True
    reverted = store.status()["head"]
    assert reverted not in {first, rename, previous}
    assert store.show(reverted)["parents"] == [previous]
    assert store.load().get("scene").label == "Original"
    assert store.load().get("scene").attributes == {"later_note": "preserve this"}
    assert store.load(rename).get("scene").label == "Changed label"


def test_revert_that_breaks_later_prerequisite_is_rejected_without_losing_work(store):
    graph = StoryGraph(Project(title="Key prerequisite", initial_state=State(values={"resource.key": False})))
    store.commit(graph, message="Before provision")
    provision = store.load()
    provision.add_node(Node(id="provide", kind="Event", label="Provide key", time=1,
                            transition=Transition(effects={"resource.key": True})))
    provision_commit = store.commit(provision, message="Provide the key")
    consumer = store.load()
    consumer.add_node(Node(id="consume", kind="Event", label="Use key", time=2,
                           transition=Transition(requires={"resource.key": True})))
    current = store.commit(consumer, message="Use the key later")
    before = store.load().document.model_dump(mode="json")
    result = store.revert(provision_commit)
    assert result["status"] == "invalid" and result["committed"] is False
    assert any(finding["code"] == "PRECONDITION" for finding in result["findings"])
    assert store.status()["head"] == current
    assert store.load().document.model_dump(mode="json") == before


def test_revert_of_merge_commit_requires_explicit_mainline_support(store):
    store.commit(story(), message="Opening")
    store.create_branch("alternate")
    commit_label(store, "Main label")
    store.checkout("alternate")
    draft = store.load()
    draft.update_node("scene", {"attributes": {"detail": "alternate"}})
    store.commit(draft, message="Alternate detail")
    store.checkout("main")
    assert store.merge("alternate")["committed"] is True
    merged = store.status()["head"]
    before = store.load().document.model_dump(mode="json")
    with pytest.raises((GraphError, ValueError), match="merge|mainline|parent"):
        store.revert(merged)
    assert store.status()["head"] == merged
    assert store.load().document.model_dump(mode="json") == before
