"""Additional end-to-end checks for permission boundaries and recovery paths."""

import json

import pytest

from narrative.cli import main
from narrative.core.schema import Node, Project
from narrative.core.versioning import SnapshotStore


def command(capsys, db, *arguments, expected=0):
    code = main(["--db", str(db), *arguments])
    captured = capsys.readouterr()
    assert code == expected, captured.out
    assert not captured.err
    payload = json.loads(captured.out)
    if expected:
        assert (payload.get("error") and payload.get("message")) or payload.get("status") in {"conflicts", "invalid"}
    return payload


def initialize(tmp_path, capsys, *, protected=None):
    db = tmp_path / "review.db"
    source = tmp_path / "original.json"
    source.write_text(Project(title="Recovery fixture", nodes=[
        Node(id="STORY", kind="Story", label="Original story", locked=protected == "locked"),
        Node(id="SCENE", kind="Scene", label="Original scene", parent_id="STORY", level=1,
             status="PROPOSED" if protected == "promotion" else "CANON"),
    ]).model_dump_json(indent=2), encoding="utf-8")
    initial = command(capsys, db, "ingest", str(source))["version"]
    return db, initial


def edit_file(tmp_path, db, filename="draft.json", node="STORY", **changes):
    store = SnapshotStore(db)
    try:
        graph = store.load()
    finally:
        store.close()
    graph.update_node(node, changes, authorized=True)
    path = tmp_path / filename
    path.write_text(graph.document.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_detached_cli_commit_remains_discoverable_and_can_be_named(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    command(capsys, db, "tag", "reviewed")
    assert command(capsys, db, "checkout", "reviewed")["detached"] is True
    draft = edit_file(tmp_path, db, label="Detached experiment")
    command(capsys, db, "save", str(draft))
    detached = command(capsys, db, "commit", "-m", "Try an unreferenced variation")
    commit_id = detached["version"]
    assert detached["detached"] is True and detached["branch"] is None
    assert command(capsys, db, "show", commit_id)["parents"] == [initial]
    branches = command(capsys, db, "branch")["branches"]
    assert {branch["name"]: branch["target"] for branch in branches} == {"main": initial}
    command(capsys, db, "switch", "main")
    assert command(capsys, db, "status")["head"] == initial
    assert commit_id in {entry["id"] for entry in command(capsys, db, "log", "--all")["log"]}
    command(capsys, db, "branch", "rescued", "--start", commit_id)
    command(capsys, db, "switch", "rescued")
    document = command(capsys, db, "show")["document"]
    assert next(node for node in document["nodes"] if node["id"] == "STORY")["label"] == "Detached experiment"


def test_matching_branch_and_tag_names_require_qualified_checkout_but_switch_attaches(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    command(capsys, db, "branch", "review")
    draft = edit_file(tmp_path, db, label="Later main revision")
    command(capsys, db, "save", str(draft))
    later = command(capsys, db, "commit", "-m", "Later main revision")["version"]
    command(capsys, db, "tag", "review", "--at", later)
    attached = command(capsys, db, "switch", "review")
    assert attached["branch"] == "review" and attached["head"] == initial
    before = command(capsys, db, "status")
    command(capsys, db, "checkout", "review", expected=2)
    assert command(capsys, db, "status") == before
    detached = command(capsys, db, "checkout", "refs/tags/review")
    assert detached["detached"] is True and detached["head"] == later
    attached = command(capsys, db, "checkout", "refs/heads/review")
    assert attached["detached"] is False and attached["head"] == initial


@pytest.mark.parametrize("protected,node,changes", [
    ("locked", "STORY", {"label": "Authorized new label"}),
    ("promotion", "SCENE", {"status": "CANON"}),
])
def test_authorization_is_required_for_both_save_and_final_cli_commit(
        tmp_path, capsys, protected, node, changes):
    db, initial = initialize(tmp_path, capsys, protected=protected)
    draft = edit_file(tmp_path, db, node=node, **changes)
    command(capsys, db, "save", str(draft), expected=2)
    status = command(capsys, db, "status")
    assert status["head"] == initial and status["dirty"] is False
    wrong_id = "SCENE" if node == "STORY" else "STORY"
    command(capsys, db, "save", str(draft), "--authorize-locked", wrong_id, expected=2)
    saved = command(capsys, db, "save", str(draft), "--authorize-locked", node)
    assert saved["head"] == initial and saved["dirty"] is True
    command(capsys, db, "commit", "-m", "Missing final authorization", expected=2)
    pending = command(capsys, db, "status")
    assert pending["head"] == initial and pending["dirty"] is True
    assert len(command(capsys, db, "log", "--all")["log"]) == 1
    committed = command(capsys, db, "commit", "-m", "Authorize this exact change", "--authorize-locked", node)
    assert committed["committed"] is True and committed["dirty"] is False
    assert committed["head"] != initial


@pytest.mark.parametrize("arguments", [
    ("show", "unknown-revision"),
    ("checkout", "unknown-revision"),
    ("branch", "unused", "--start", "unknown-revision"),
    ("tag", "unused", "--at", "unknown-revision"),
    ("log", "--limit", "-1"),
    ("merge", "--abort"),
    ("merge", "--resolve", "/nodes/STORY/label=ours"),
])
def test_invalid_cli_references_and_recovery_actions_emit_json_without_state_changes(
        tmp_path, capsys, arguments):
    db, _ = initialize(tmp_path, capsys)
    before = command(capsys, db, "status")
    command(capsys, db, *arguments, expected=2)
    assert command(capsys, db, "status") == before
    assert len(command(capsys, db, "history")["history"]) == 1


def test_invalid_source_files_emit_json_and_leave_persistent_draft_untouched(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    draft = edit_file(tmp_path, db, label="Preserve this draft")
    command(capsys, db, "save", str(draft))
    before = command(capsys, db, "status")
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"title": "truncated"', encoding="utf-8")
    command(capsys, db, "save", str(malformed), expected=2)
    command(capsys, db, "save", str(tmp_path / "missing.json"), expected=2)
    assert command(capsys, db, "status") == before
    assert command(capsys, db, "show", initial)["document"]["title"] == "Recovery fixture"
    exported = tmp_path / "preserved.json"
    command(capsys, db, "export", "--format", "json", "--output", str(exported))
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert next(node for node in document["nodes"] if node["id"] == "STORY")["label"] == "Preserve this draft"


def test_clean_cli_commit_is_an_explicit_json_error_without_a_new_event(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    before = command(capsys, db, "status")
    failure = command(capsys, db, "commit", "-m", "There are no edits", expected=2)
    assert "nothing to commit" in failure["message"].lower()
    assert command(capsys, db, "status") == before
    assert command(capsys, db, "status")["head"] == initial
    assert len(command(capsys, db, "history")["history"]) == 1


@pytest.mark.parametrize("message", ["", " ", "\n\t"])
def test_blank_cli_commit_messages_do_not_consume_dirty_work(tmp_path, capsys, message):
    db, _ = initialize(tmp_path, capsys)
    draft = edit_file(tmp_path, db, label="Keep this uncommitted change")
    command(capsys, db, "save", str(draft))
    before = command(capsys, db, "status")
    command(capsys, db, "commit", "-m", message, expected=2)
    assert command(capsys, db, "status") == before
    assert before["dirty"] is True
    assert len(command(capsys, db, "history")["history"]) == 1


def prepare_two_conflicts(tmp_path, capsys, db):
    command(capsys, db, "branch", "alternate")
    ours = edit_file(tmp_path, db, label="Main label", purpose="Main purpose", attributes={"main": True})
    command(capsys, db, "save", str(ours))
    main = command(capsys, db, "commit", "-m", "Main changes")["version"]
    command(capsys, db, "switch", "alternate")
    theirs = edit_file(tmp_path, db, filename="alternate.json", label="Alternate label",
                       purpose="Alternate purpose", attributes={"alternate": True})
    command(capsys, db, "save", str(theirs))
    alternate = command(capsys, db, "commit", "-m", "Alternate changes")["version"]
    command(capsys, db, "switch", "main")
    return main, alternate


def test_partial_cli_resolution_survives_errors_and_requires_explicit_final_commit(tmp_path, capsys):
    db, _ = initialize(tmp_path, capsys)
    main, alternate = prepare_two_conflicts(tmp_path, capsys, db)
    conflict = command(capsys, db, "merge", "alternate", expected=2)
    paths = {entry["path"].rsplit("/", 1)[-1]: entry["path"] for entry in conflict["conflicts"]}
    assert set(paths) == {"label", "purpose"}
    partial = command(capsys, db, "merge", "--resolve", f"{paths['label']}=theirs", expected=2)
    assert partial["status"] == "conflicts" and partial["committed"] is False
    before = command(capsys, db, "status")
    command(capsys, db, "merge", "--resolve", "/nodes/DOES_NOT_EXIST/label=ours", expected=2)
    command(capsys, db, "commit", "-m", "Cannot commit unresolved purpose", expected=2)
    assert command(capsys, db, "status") == before
    resolved = command(capsys, db, "merge", "--resolve", f"{paths['purpose']}=ours")
    assert resolved["status"] == "resolved" and resolved["committed"] is False
    assert command(capsys, db, "status")["head"] == main
    merged = command(capsys, db, "commit", "-m", "Resolve both conflicts")
    assert command(capsys, db, "show", merged["version"])["parents"] == [main, alternate]
    node = next(node for node in command(capsys, db, "show")["document"]["nodes"] if node["id"] == "STORY")
    assert node["label"] == "Alternate label" and node["purpose"] == "Main purpose"
    assert node["attributes"] == {"main": True, "alternate": True}
