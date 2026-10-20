import json

from narrative.cli import main
from narrative.core.schema import Node, Project
from narrative.core.versioning import SnapshotStore


def run(capsys, db, *args, expected=0):
    assert main(["--db", str(db), *args]) == expected
    return json.loads(capsys.readouterr().out)


def initialize(tmp_path, capsys):
    db = tmp_path / "story.db"
    source = tmp_path / "initial.json"
    source.write_text(Project(title="Revision fixture", nodes=[
        Node(id="STORY", kind="Story", label="Original story", attributes={"left": 0, "right": 0}),
        Node(id="SCENE", kind="Scene", label="Original scene", parent_id="STORY", level=1),
    ]).model_dump_json(indent=2), encoding="utf-8")
    initial = run(capsys, db, "ingest", str(source))
    return db, initial["version"]


def save_edit(tmp_path, capsys, db, filename="draft.json", **changes):
    store = SnapshotStore(db)
    try:
        graph = store.load()
    finally:
        store.close()
    graph.update_node("STORY", changes)
    path = tmp_path / filename
    path.write_text(graph.document.model_dump_json(indent=2), encoding="utf-8")
    return run(capsys, db, "save", str(path))


def test_working_copy_branches_tags_and_revision_inspection(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    status = run(capsys, db, "status")
    assert status["branch"] == "main" and status["head"] == initial
    assert not status["dirty"] and not status["detached"]
    run(capsys, db, "branch", "alternate")
    assert run(capsys, db, "status")["branch"] == "main"
    assert {item["name"] for item in run(capsys, db, "branch")["branches"]} == {"main", "alternate"}
    assert run(capsys, db, "switch", "alternate")["branch"] == "alternate"
    saved = save_edit(tmp_path, capsys, db, label="Alternate story")
    assert saved["dirty"] and saved["head"] == initial
    assert run(capsys, db, "diff")["nodes"]["changed"] == ["STORY"]
    assert run(capsys, db, "diff", initial)["nodes"]["changed"] == ["STORY"]
    working = run(capsys, db, "export", "--format", "json", "--output", str(tmp_path / "working.json"))
    assert working["version"].startswith("working:")
    committed = run(capsys, db, "commit", "-m", "Change alternate label")
    assert committed["committed"] and not committed["dirty"]
    alternate = committed["version"]
    assert alternate != initial
    assert run(capsys, db, "diff", initial, alternate)["nodes"]["changed"] == ["STORY"]
    run(capsys, db, "tag", "reviewed", "--at", alternate)
    assert run(capsys, db, "tag")["tags"][0]["name"] == "reviewed"
    assert run(capsys, db, "show", "reviewed")["document"]["nodes"][0]["label"] == "Alternate story"
    assert len(run(capsys, db, "log", "--all", "--limit", "20")["log"]) == 2
    assert run(capsys, db, "show", "HEAD~1")["document"]["title"] == "Revision fixture"
    assert run(capsys, db, "checkout", "reviewed")["detached"]
    assert run(capsys, db, "switch", "main")["head"] == initial
    assert not run(capsys, db, "status")["detached"]
    assert run(capsys, db, "show", alternate[:8])["document"]["title"] == "Revision fixture"


def test_dirty_checkout_refused_until_explicit_discard(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    run(capsys, db, "branch", "alternate")
    save_edit(tmp_path, capsys, db, label="Uncommitted edit")
    error = run(capsys, db, "checkout", "alternate", expected=2)
    assert "dirty" in error["message"].lower() or "uncommitted" in error["message"].lower()
    status = run(capsys, db, "status")
    assert status["dirty"] and status["branch"] == "main"
    shown = run(capsys, db, "show", initial)
    assert any(node["label"] == "Original story" for node in shown["document"]["nodes"])
    result = run(capsys, db, "checkout", "alternate", "--discard-changes")
    assert result["branch"] == "alternate" and not result["dirty"]


def test_switch_rejects_tag_and_commit_revisions(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    run(capsys, db, "tag", "review")
    run(capsys, db, "switch", "review", expected=2)
    run(capsys, db, "switch", initial, expected=2)
    assert run(capsys, db, "status")["branch"] == "main"


def test_refine_commits_from_dirty_working_copy_using_head_parent(tmp_path, capsys):
    db = tmp_path / "story.db"
    initial = run(capsys, db, "init", "--example")["version"]
    save_edit(tmp_path, capsys, db, purpose="A saved uncommitted premise adjustment")
    assert run(capsys, db, "status")["dirty"]
    refined = run(capsys, db, "refine", "--node", "ACT_1", "--depth", "1", "--max-nodes", "2")
    assert refined["children"] and refined["version"] != initial
    latest = run(capsys, db, "log", "--limit", "1")["log"][0]
    assert latest["parents"] == [initial]
    assert not run(capsys, db, "status")["dirty"]


def test_divergent_merge_commit_and_inverse_revert_preserve_later_edits(tmp_path, capsys):
    db, initial = initialize(tmp_path, capsys)
    run(capsys, db, "branch", "alternate")
    save_edit(tmp_path, capsys, db, attributes={"left": 1, "right": 0})
    ours = run(capsys, db, "commit", "-m", "Main left edit")["version"]
    run(capsys, db, "switch", "alternate")
    save_edit(tmp_path, capsys, db, attributes={"left": 0, "right": 2})
    theirs = run(capsys, db, "commit", "-m", "Alternate right edit")["version"]
    run(capsys, db, "switch", "main")
    merged = run(capsys, db, "merge", "alternate", "-m", "Combine independent fields")
    assert merged["status"] == "merged" and merged["committed"]
    latest = run(capsys, db, "log", "--limit", "1")["log"][0]
    assert latest["parents"] == [ours, theirs]
    attrs = next(node["attributes"] for node in run(capsys, db, "show")["document"]["nodes"] if node["id"] == "STORY")
    assert attrs == {"left": 1, "right": 2}
    reverted = run(capsys, db, "revert", ours, "-m", "Undo the left edit")
    assert reverted["committed"]
    attrs = next(node["attributes"] for node in run(capsys, db, "show")["document"]["nodes"] if node["id"] == "STORY")
    assert attrs == {"left": 0, "right": 2}
    assert run(capsys, db, "show", initial)["document"]["nodes"]


def test_merge_conflict_resolution_requires_explicit_commit_and_can_abort(tmp_path, capsys):
    db, _ = initialize(tmp_path, capsys)
    run(capsys, db, "branch", "alternate")
    save_edit(tmp_path, capsys, db, label="Main version")
    main = run(capsys, db, "commit", "-m", "Main label")["version"]
    run(capsys, db, "switch", "alternate")
    save_edit(tmp_path, capsys, db, label="Alternate version")
    alternate = run(capsys, db, "commit", "-m", "Alternate label")["version"]
    run(capsys, db, "switch", "main")
    conflict = run(capsys, db, "merge", "alternate", expected=2)
    assert conflict["status"] == "conflicts" and not conflict["committed"]
    assert run(capsys, db, "status")["head"] == main
    path = conflict["conflicts"][0]["path"]
    assert path.endswith("/label")
    assert run(capsys, db, "merge", "--abort")["status"] == "aborted"
    assert run(capsys, db, "status")["head"] == main
    conflict = run(capsys, db, "merge", "alternate", expected=2)
    resolved = run(capsys, db, "merge", "--resolve", f"{path}=theirs")
    assert resolved["status"] == "resolved" and not resolved["committed"]
    assert run(capsys, db, "status")["head"] == main
    run(capsys, db, "commit", "-m", "Choose alternate label")
    latest = run(capsys, db, "log", "--limit", "1")["log"][0]
    assert latest["parents"] == [main, alternate]


def test_new_cli_argument_failures_are_json_and_nonzero(tmp_path, capsys):
    db, _ = initialize(tmp_path, capsys)
    invalid_commands = [
        ("commit",), ("branch", "--start", "HEAD"), ("tag", "--at", "HEAD"),
        ("diff", "HEAD", "HEAD", "HEAD"), ("merge",),
        ("merge", "HEAD", "--abort"), ("merge", "--resolve", "bad"),
        ("merge", "--resolve", "/nodes/STORY/label=unknown"),
        ("merge", "--resolve", "/nodes/STORY/label=ours", "--message", "no"),
    ]
    for arguments in invalid_commands:
        payload = run(capsys, db, *arguments, expected=2)
        assert payload["error"] and payload["message"]
