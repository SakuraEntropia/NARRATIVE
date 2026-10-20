"""JSON CLI. Mutations that establish canon require an explicit approval flag."""

import argparse
import dataclasses
import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from .core.graph import StoryGraph
from .core.schema import Project
from .core.state_machine import simulate
from .core.versioning import SnapshotStore


def plain(value):
    if isinstance(value, StoryGraph):
        return value.document.model_dump(mode="json")
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return {field.name: plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    return value


def emit(value):
    print(json.dumps(plain(value), ensure_ascii=False, indent=2, allow_nan=False))


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def parser():
    root = JsonArgumentParser(prog="narrative", description=__doc__)
    root.add_argument("--db", default="narrative.db", help="Local project SQLite path (use before command)")
    root.add_argument("--json", action="store_true", help="All commands already emit JSON")
    commands = root.add_subparsers(dest="command", required=True)

    def command(name, help):
        child = commands.add_parser(name, help=help)
        child.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
        return child

    init = command("init", "Initialize an empty project or original demonstration")
    init.add_argument("--example", action="store_true")
    init.add_argument("--title", default="Untitled story")
    ingest = command("ingest", "Validate and import a story JSON document")
    ingest.add_argument("path", type=Path)
    command("compile", "Validate and chronologically simulate canonical events")
    refine = command("refine", "Save bounded PROPOSED detail; never promote canon")
    refine.add_argument("--node", required=True)
    refine.add_argument("--depth", type=int, default=2)
    refine.add_argument("--max-nodes", type=int, default=12)
    analyze = command("analyze", "Compute sparse attention and polyphony projections")
    analyze.add_argument("--attention", action="store_true")
    analyze.add_argument("--polyphony", action="store_true")
    evaluate = command("evaluate", "Return evidence-bearing B1–B9 reports")
    evaluate.add_argument("--benchmark", choices=["all", *[f"B{i}" for i in range(1, 10)]], default="all")
    pivot = command("pivot", "Preview or explicitly approve an isolated revision")
    pivot.add_argument("--target", required=True)
    pivot.add_argument("--candidate", type=int, default=0)
    pivot.add_argument("--approve", action="store_true")
    pivot.add_argument("--authorize-locked", action="append", default=[])
    duel = command("duel", "Compare bounded revision candidates and critic disagreements")
    duel.add_argument("--candidates", type=int, default=3)
    duel.add_argument("--target", default="CLIMAX")
    command("audit", "Run a full graph/state/evaluation audit")
    command("history", "List immutable versions")
    command("status", "Inspect HEAD, branch and uncommitted story changes")
    save = command("save", "Validate and save a whole-story JSON working copy")
    save.add_argument("path", type=Path)
    save.add_argument("--authorize-locked", action="append", default=[])
    commit = command("commit", "Commit the saved working copy")
    commit.add_argument("-m", "--message", required=True)
    commit.add_argument("--author", default="human")
    commit.add_argument("--authorize-locked", action="append", default=[])
    branch = command("branch", "List branches or create one without switching")
    branch.add_argument("name", nargs="?")
    branch.add_argument("--start")
    tag = command("tag", "List tags or create an immutable named revision")
    tag.add_argument("name", nargs="?")
    tag.add_argument("--at")
    checkout = command("checkout", "Load a revision; branches attach HEAD, other revisions detach")
    checkout.add_argument("revision")
    checkout.add_argument("--discard-changes", action="store_true")
    switch = command("switch", "Switch to a named story branch")
    switch.add_argument("branch")
    log = command("log", "Inspect commit ancestry and merge parents")
    log.add_argument("revision", nargs="?", default="HEAD")
    log.add_argument("--all", action="store_true", dest="all_branches")
    log.add_argument("--limit", type=int, default=100)
    reflog = command("reflog", "Inspect HEAD/ref operations and recover earlier commit IDs")
    reflog.add_argument("--limit", type=int, default=100)
    show = command("show", "Inspect immutable commit metadata and story document")
    show.add_argument("revision", nargs="?", default="HEAD")
    merge = command("merge", "Merge a revision, resolve reported conflicts, or abort")
    merge.add_argument("revision", nargs="?")
    merge.add_argument("-m", "--message")
    merge.add_argument("--authorize-locked", action="append", default=[])
    merge.add_argument("--resolve", action="append", default=[], metavar="PATH=CHOICE")
    merge.add_argument("--abort", action="store_true")
    revert = command("revert", "Apply an inverse commit delta while preserving later edits")
    revert.add_argument("revision")
    revert.add_argument("-m", "--message")
    revert.add_argument("--authorize-locked", action="append", default=[])
    diff = command("diff", "Compare HEAD to working, revision to working, or two revisions")
    diff.add_argument("revisions", nargs="*", metavar="REV")
    export = command("export", "Export computed inspection data")
    export.add_argument("--format", choices=["html", "json"], default="html")
    export.add_argument("--output", type=Path, default=Path("story.html"))
    experiments = command("experiments", "Run reproducible original experiments A–G")
    experiments.add_argument("--output", type=Path)
    return root


def execute(args):
    if args.command == "experiments":
        from .experiments import run_experiments
        result = run_experiments()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(plain(result), ensure_ascii=False, indent=2), encoding="utf-8")
        return result, 0

    store = SnapshotStore(args.db)
    try:
        action = args.command
        if action == "init":
            if store.history():
                raise ValueError("Database already has a project; use a new --db path")
            if args.example:
                from .examples import example_graph
                graph = example_graph()
            else:
                graph = StoryGraph(Project(title=args.title))
            version = store.commit(graph, message="Initialize project")
            return {"version": version, "title": graph.document.title, "nodes": len(graph.nodes)}, 0
        if action == "ingest":
            graph = StoryGraph(Project.model_validate_json(args.path.read_text(encoding="utf-8")))
            version = store.commit(graph, message=f"Import {args.path.name}")
            return {"version": version, "nodes": len(graph.nodes), "edges": len(graph.edges)}, 0
        if action == "history":
            return {"history": store.history()}, 0
        if action == "status":
            return store.status(), 0
        if action == "save":
            graph = StoryGraph(Project.model_validate_json(args.path.read_text(encoding="utf-8")))
            return store.save_working(graph, authorized_locked=args.authorize_locked), 0
        if action == "commit":
            version = store.commit_working(args.message, author=args.author, authorized_locked=args.authorize_locked)
            return {"version": version, "committed": True, **store.status()}, 0
        if action == "branch":
            if args.name is None:
                if args.start is not None:
                    raise ValueError("branch --start requires a branch name")
                return {"branches": store.branches()}, 0
            return store.create_branch(args.name, start=args.start), 0
        if action == "tag":
            if args.name is None:
                if args.at is not None:
                    raise ValueError("tag --at requires a tag name")
                return {"tags": store.tags()}, 0
            return store.create_tag(args.name, target=args.at), 0
        if action == "checkout":
            return store.checkout(args.revision, discard_changes=args.discard_changes), 0
        if action == "switch":
            names = {item["name"] for item in store.branches()}
            if args.branch not in names:
                raise ValueError(f"Unknown branch: {args.branch}; switch requires an existing branch")
            result = store.checkout(f"refs/heads/{args.branch}")
            if result.get("detached") or result.get("branch") != args.branch:
                raise ValueError("Switch did not attach the requested branch")
            return result, 0
        if action == "log":
            return {"log": store.log(args.revision, all_branches=args.all_branches, limit=args.limit)}, 0
        if action == "reflog":
            return {"reflog": store.reflog(limit=args.limit)}, 0
        if action == "show":
            return store.show(args.revision), 0
        if action == "merge":
            selected = int(args.revision is not None) + int(bool(args.resolve)) + int(args.abort)
            if selected != 1:
                raise ValueError("Choose exactly one merge revision, --resolve PATH=ours|theirs|base, or --abort")
            if args.revision is not None:
                result = store.merge(args.revision, message=args.message, authorized_locked=args.authorize_locked)
            else:
                if args.message or args.authorize_locked:
                    raise ValueError("Use -m and --authorize-locked with merge REV or the final commit")
                if args.abort:
                    result = store.abort_merge()
                else:
                    resolutions = {}
                    for specification in args.resolve:
                        if "=" not in specification:
                            raise ValueError("Conflict resolution must be PATH=ours|theirs|base")
                        path, choice = specification.rsplit("=", 1)
                        if not path.startswith("/") or choice not in {"ours", "theirs", "base"}:
                            raise ValueError("Conflict resolution requires a JSON pointer path and ours, theirs, or base")
                        if path in resolutions and resolutions[path] != choice:
                            raise ValueError(f"Conflicting choices for path: {path}")
                        resolutions[path] = choice
                    result = store.resolve_conflicts(resolutions)
            return result, 2 if result.get("status") in {"conflicts", "invalid"} else 0
        if action == "revert":
            result = store.revert(args.revision, message=args.message, authorized_locked=args.authorize_locked)
            return result, 2 if result.get("status") in {"conflicts", "invalid"} else 0
        if action == "diff":
            if len(args.revisions) > 2:
                raise ValueError("diff accepts zero, one, or two revisions")
            return store.diff(*args.revisions), 0
        graph = store.load()
        if action == "compile":
            result = simulate(graph)
            return result, 2 if any(f.severity == "error" for f in result.findings) else 0
        if action == "refine":
            from .refinement import refine
            result = refine(graph, args.node, depth=args.depth, max_nodes=args.max_nodes)
            if result.children:
                version = store.commit(result.graph, parent=store.status()["head"], message=f"Proposed refinement of {args.node}")
            else:
                version = graph.document.version
            payload = {key: plain(getattr(result, key)) for key in ("children", "checkpoints", "feedback", "telemetry", "stopped_reason")}
            payload["version"] = version
            return payload, 0 if result.children else 2
        if action == "analyze":
            from .analysis.attention import analyze_attention
            from .analysis.polyphony import analyze_polyphony
            result = {}
            if args.attention or not args.polyphony:
                result["attention"] = analyze_attention(graph)
            if args.polyphony or not args.attention:
                result["polyphony"] = analyze_polyphony(graph)
            return result, 0
        if action == "evaluate":
            from .evaluation.benchmarks import evaluate
            result = evaluate(graph)
            if args.benchmark != "all":
                result["dimensions"] = {args.benchmark: result["dimensions"][args.benchmark]}
            return result, 0
        if action == "pivot":
            from .optimization import backward_influence, evaluate_pivot, propose_pivots
            pivots = propose_pivots(graph, args.target)
            if args.approve:
                if args.candidate < 0 or args.candidate >= len(pivots):
                    raise ValueError("Candidate index is out of range")
                result = evaluate_pivot(graph, pivots[args.candidate], approve=True, authorized_locked=args.authorize_locked)
                report = result["report"]
                if not report.get("valid", False):
                    return {"report": report, "committed": False}, 2
                version = store.commit(result["branch"], parent=store.status()["head"],
                                       message=f"Approved pivot {args.candidate} for {args.target}",
                                       authorized_locked=args.authorize_locked)
                return {"version": version, "report": report, "committed": True}, 0
            return {"backward_influence": backward_influence(graph, args.target),
                    "candidates": [evaluate_pivot(graph, p)["report"] for p in pivots],
                    "committed": False}, 0
        if action == "duel":
            from .optimization import duel, propose_pivots
            if not 1 <= args.candidates <= 32:
                raise ValueError("Candidate count must be between 1 and 32")
            return duel(graph, propose_pivots(graph, args.target, max_candidates=args.candidates), max_candidates=args.candidates), 0
        if action == "audit":
            from .evaluation.benchmarks import evaluate
            from .evaluation.adversarial import review
            simulation = simulate(graph)
            return {"graph_findings": graph.validate(), "simulation": simulation,
                    "benchmark": evaluate(graph), "critics": review(graph), "scope": "full_graph"}, 2 if any(f.severity == "error" for f in simulation.findings) else 0
        if action == "export":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.format == "json":
                args.output.write_text(graph.document.model_dump_json(indent=2), encoding="utf-8")
            else:
                from .visualization import export_html
                export_html(graph, args.output)
            return {"path": str(args.output.resolve()), "format": args.format, "version": graph.document.version}, 0
        raise ValueError(f"Unknown command: {action}")
    finally:
        store.close()


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        value, status = execute(args)
        emit(value)
        return status
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        emit({"error": type(error).__name__, "message": str(error)})
        return 2
