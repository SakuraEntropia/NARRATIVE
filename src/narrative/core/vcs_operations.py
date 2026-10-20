"""Atomic merge/revert lifecycle over the immutable story commit DAG.

Unresolved operations persist choices and tentative work without advancing HEAD.
The persistence store owns transaction and stale-writer checks.
"""

import json

from pydantic import ValidationError

from .graph import GraphError, StoryGraph
from .merge import merge_documents
from .schema import Project
from .state_machine import simulate
from .vcs_storage import encode_document


def _ancestors(store, identifier):
    visited, pending = set(), [identifier]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(store._commit_record(current)["parents"])
    return visited


def _merge_base(store, ours, theirs):
    common = _ancestors(store, ours) & _ancestors(store, theirs)
    if not common:
        raise GraphError("Cannot merge unrelated histories")
    maximal = set(common)
    for candidate in common:
        maximal.difference_update(_ancestors(store, candidate) - {candidate})
    if len(maximal) != 1:
        raise GraphError("Multiple merge bases require recursive-base support; merge is ambiguous")
    return maximal.pop()


def _clean_head(store):
    state = store._state()
    if state["pending"]:
        raise GraphError("Pending merge/revert; resolve and commit or abort before another operation")
    head = store._head(state)
    if head is None:
        raise GraphError("No story loaded; run ingest or init --example")
    if store.status()["dirty"]:
        raise GraphError("Uncommitted working changes; commit them before merge or revert")
    return head


def _finding_key(finding):
    return finding.code, tuple(finding.node_ids), tuple(finding.evidence), finding.message


def _validate_result(store, graph, ours, protected, authorized):
    """Require structural validity and no new simulation errors versus HEAD."""
    for previous in protected:
        store._guard(previous, graph, authorized)
    findings = [f.model_dump(mode="json") for f in graph.validate() if f.severity == "error"]
    if findings:
        return findings
    baseline = {_finding_key(f) for f in simulate(ours).findings if f.severity == "error"}
    findings.extend(f.model_dump(mode="json") for f in simulate(graph).findings
                    if f.severity == "error" and _finding_key(f) not in baseline)
    return findings


def _graph(document):
    return StoryGraph(Project.model_validate(document))


def _invalid(findings):
    return {"status": "invalid", "committed": False, "findings": findings}


def _stage(store, operation, merged, graph):
    """Persist a provisional document only after enforcing canon permissions."""
    operation["conflicts"] = merged["conflicts"]
    store.connection.execute(
        "UPDATE vcs_state SET work=?,pending=?,revision=revision+1 WHERE singleton=1",
        (encode_document(graph.document), json.dumps(operation, ensure_ascii=False)),
    )
    store._reflog(operation["kind"] + "_stage", operation["ours"], operation["ours"],
                   {"remaining_conflicts": len(merged["conflicts"])})


def _operation(store, kind, ours, base, theirs, message, authorized, source=None):
    state = store._state()
    operation = {"kind": kind, "ours": ours, "base": base, "theirs": theirs,
                 "parents": [ours, theirs] if kind == "merge" else [ours],
                 "message": message, "source": source, "resolutions": {},
                 "authorized_locked": sorted(set(authorized or [])),
                 "original_work": state["work"], "original_base": state["base"]}
    merged = merge_documents(store._at(base).document.model_dump(mode="json"),
                             store._at(ours).document.model_dump(mode="json"),
                             store._at(theirs).document.model_dump(mode="json"))
    try:
        graph = _graph(merged["document"])
    except ValidationError as error:
        return _invalid([{"code": "SCHEMA", "message": str(error)}])
    protected = [store._at(ours)]
    if kind == "merge":
        protected.append(store._at(theirs))
    for previous in protected:
        store._guard(previous, graph, authorized)
    if merged["conflicts"]:
        _stage(store, operation, merged, graph)
        return {"status": "conflicts", "committed": False, "head": ours,
                "conflicts": merged["conflicts"], "operation": kind}
    findings = _validate_result(store, graph, store._at(ours), protected, authorized)
    if findings:
        return _invalid(findings)
    metadata = {"operation": kind, "base": base, "source": source or theirs}
    version = store._record(graph, operation["parents"], message, metadata=metadata)
    return {"status": "merged" if kind == "merge" else "reverted", "committed": True,
            "version": version, "parents": operation["parents"]}


def commit_working(store, message, author="human", authorized_locked=None):
    if not isinstance(message, str) or not message.strip():
        raise GraphError("Commit message must not be blank")
    if not isinstance(author, str) or not author.strip():
        raise GraphError("Commit author must not be blank")
    with store._write():
        state = store._state()
        graph = store._working()
        head = store._head(state)
        pending = json.loads(state["pending"]) if state["pending"] else None
        if pending:
            if pending["ours"] != head:
                raise GraphError("Pending operation HEAD changed; abort and retry")
            if pending["conflicts"]:
                raise GraphError("Unresolved conflicts; choose each conflict before committing")
            protected = [store._at(head)]
            if pending["kind"] == "merge":
                protected.append(store._at(pending["theirs"]))
            findings = _validate_result(store, graph, store._at(head), protected, authorized_locked)
            if findings:
                raise GraphError("Invalid resolved story; abort or revise conflict choices: " +
                                 "; ".join(f["message"] for f in findings))
            parents = pending["parents"]
            metadata = {"operation": pending["kind"], "base": pending["base"],
                        "source": pending.get("source") or pending["theirs"],
                        "resolutions": pending["resolutions"]}
        else:
            if not store.status()["dirty"]:
                raise GraphError("Nothing to commit: working copy is clean")
            store._validate(graph)
            store._guard(store._at(head) if head else None, graph, authorized_locked)
            parents, metadata = [head] if head else [], {}
        return store._record(graph, parents, message, author, metadata)


def merge(store, revision, message=None, authorized_locked=None):
    with store._write():
        ours = _clean_head(store)
        theirs = store.resolve(revision)
        if theirs in _ancestors(store, ours):
            return {"status": "up_to_date", "committed": False, "head": ours}
        if ours in _ancestors(store, theirs):
            current, target = store._at(ours), store._at(theirs)
            findings = _validate_result(store, target, current, [current], authorized_locked)
            if findings:
                return _invalid(findings)
            store._move_head(theirs, action="fast_forward", detail={"from": ours})
            return {"status": "fast_forward", "committed": True, "version": theirs}
        base = _merge_base(store, ours, theirs)
        return _operation(store, "merge", ours, base, theirs,
                          message or f"Merge {revision}", authorized_locked)


def revert(store, revision, message=None, authorized_locked=None):
    with store._write():
        ours = _clean_head(store)
        source = store.resolve(revision)
        parents = store._commit_record(source)["parents"]
        if len(parents) != 1:
            raise GraphError("Revert requires a single parent; root and merge commits need explicit mainline support")
        # Invert source→parent against current HEAD, retaining later unrelated edits.
        return _operation(store, "revert", ours, source, parents[0],
                          message or f"Revert {source[:12]}", authorized_locked, source)


def resolve_conflicts(store, resolutions):
    with store._write():
        state = store._state()
        if not state["pending"]:
            raise GraphError("No pending merge or revert to resolve")
        pending = json.loads(state["pending"])
        if store._head(state) != pending["ours"]:
            raise GraphError("Pending operation HEAD changed; abort and retry")
        if not isinstance(resolutions, dict) or not resolutions:
            raise GraphError("Provide at least one conflict resolution")
        choices = {**pending["resolutions"], **resolutions}
        merged = merge_documents(store._at(pending["base"]).document.model_dump(mode="json"),
                                 store._at(pending["ours"]).document.model_dump(mode="json"),
                                 store._at(pending["theirs"]).document.model_dump(mode="json"), choices)
        try:
            graph = _graph(merged["document"])
        except ValidationError as error:
            return _invalid([{"code": "SCHEMA", "message": str(error)}])
        protected = [store._at(pending["ours"])]
        if pending["kind"] == "merge":
            protected.append(store._at(pending["theirs"]))
        for previous in protected:
            store._guard(previous, graph, pending["authorized_locked"])
        if not merged["conflicts"]:
            findings = _validate_result(store, graph, store._at(pending["ours"]), protected,
                                        pending["authorized_locked"])
            if findings:
                return _invalid(findings)
        pending["resolutions"] = choices
        _stage(store, pending, merged, graph)
        return {"status": "conflicts" if merged["conflicts"] else "resolved", "committed": False,
                "head": pending["ours"], "conflicts": merged["conflicts"],
                "operation": pending["kind"]}


def abort_merge(store):
    with store._write():
        state = store._state()
        if not state["pending"]:
            raise GraphError("No pending merge or revert to abort")
        pending = json.loads(state["pending"])
        if store._head(state) != pending["ours"]:
            raise GraphError("Pending operation HEAD changed; cannot restore work safely")
        store.connection.execute(
            "UPDATE vcs_state SET work=?,base=?,pending=NULL,revision=revision+1 WHERE singleton=1",
            (pending["original_work"], pending["original_base"]),
        )
        store._reflog("abort_" + pending["kind"], pending["ours"], pending["ours"])
        return {"status": "aborted", "committed": False, "head": pending["ours"]}
