import json

from narrative.cli import main
from narrative.core.versioning import SnapshotStore
from narrative.examples import example_graph, story_document
from narrative.visualization import export_html


def run(capsys, db, *args, expected=0):
    assert main(["--db", str(db), *args]) == expected
    return json.loads(capsys.readouterr().out)


def test_complete_cli_workflow_and_proposed_refinement(tmp_path, capsys):
    db = tmp_path / "story.db"
    initial = run(capsys, db, "init", "--example")
    assert initial["nodes"] >= 30
    assert len(run(capsys, db, "compile")["applied"]) >= 20
    analysis = run(capsys, db, "analyze", "--attention", "--polyphony")
    assert analysis["attention"]["sparse_matrices"]["foreshadowing"]
    assert len(analysis["polyphony"]["thread_timeline"]) == 3
    assert len(run(capsys, db, "evaluate")["dimensions"]) == 9
    assert list(run(capsys, db, "evaluate", "--benchmark", "B5")["dimensions"]) == ["B5"]
    proposal = run(capsys, db, "refine", "--node", "ACT_1", "--depth", "2")
    assert proposal["children"]
    difference = run(capsys, db, "diff", initial["version"], proposal["version"])
    assert difference["nodes"]["added"] == sorted(proposal["children"])
    store = SnapshotStore(db)
    assert all(store.load().get(n).status == "PROPOSED" for n in proposal["children"])
    store.close()
    assert run(capsys, db, "pivot", "--target", "CLIMAX")["committed"] is False
    assert "pareto_set" in run(capsys, db, "duel", "--candidates", "3")
    assert run(capsys, db, "audit")["scope"] == "full_graph"
    assert len(run(capsys, db, "history")["history"]) == 2
    html = tmp_path / "story.html"
    assert run(capsys, db, "export", "--format", "html", "--output", str(html))["format"] == "html"
    assert html.exists()
    exported = tmp_path / "story.json"
    run(capsys, db, "export", "--format", "json", "--output", str(exported))
    assert json.loads(exported.read_text())["title"] == "The Last Tide Ledger"


def test_ingest_and_explicit_pivot_approval(tmp_path, capsys):
    source = tmp_path / "weak.json"
    source.write_text(json.dumps(story_document("weak_motivation")))
    db = tmp_path / "story.db"
    imported = run(capsys, db, "ingest", str(source))
    approved = run(capsys, db, "pivot", "--target", "CLIMAX", "--candidate", "0", "--approve")
    assert approved["committed"]
    assert approved["report"]["canonical_approval"]
    assert run(capsys, db, "diff", imported["version"], approved["version"])["nodes"]["changed"]


def test_errors_nonzero_and_experiments_actual_json(tmp_path, capsys):
    db = tmp_path / "empty.db"
    assert "ingest" in run(capsys, db, "compile", expected=2)["message"]
    run(capsys, db, "init", "--example")
    assert "already" in run(capsys, db, "init", expected=2)["message"]
    assert "Unknown" in run(capsys, db, "refine", "--node", "MISSING", expected=2)["message"]
    run(capsys, db, "duel", "--candidates", "999", expected=2)
    out = tmp_path / "experiments.json"
    report = run(capsys, db, "experiments", "--output", str(out))
    assert set(report["experiments"]) == set("ABCDEFG")
    assert json.loads(out.read_text())["checks"] == report["checks"]


def test_html_imported_text_cannot_escape_json_script(tmp_path):
    graph = example_graph()
    graph.update_node("ACT_1", {"label": '</script><script>window.injected=1</script>'})
    path = tmp_path / "story.html"
    export_html(graph, path)
    text = path.read_text()
    assert '</script><script>window.injected' not in text
    assert r'\u003c/script\u003e\u003cscript\u003e' in text
    assert 'textContent' in text
