"""Git-inspired story history: immutable commits, refs, HEAD and working copy."""

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .graph import GraphError, StoryGraph
from .schema import CanonStatus, Project
from .vcs_storage import commit_id, digest, encode_document, now, setup


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self._read_token = None
        try:
            setup(self.connection)
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def _state(self):
        return dict(self.connection.execute("SELECT * FROM vcs_state WHERE singleton=1").fetchone())

    def _head(self, state=None):
        state = state or self._state()
        if state["head_ref"]:
            row = self.connection.execute("SELECT target FROM vcs_refs WHERE name=?", (state["head_ref"],)).fetchone()
            return row[0] if row else None
        return state["detached"]

    def _token(self):
        state = self._state()
        return state["head_ref"], self._head(state), state["revision"]

    @contextmanager
    def _write(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if self._read_token is not None and self._read_token != self._token():
                raise GraphError("Stale working copy: HEAD or working revision changed; reload before writing")
            yield
            self.connection.commit()
            self._read_token = self._token()
        except Exception:
            self.connection.rollback()
            raise

    def _commit_record(self, identifier):
        row = self.connection.execute("SELECT * FROM vcs_commits WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise GraphError(f"Unknown snapshot or commit: {identifier}")
        result = dict(row)
        result["parents"] = json.loads(result["parents"])
        result["metadata"] = json.loads(result["metadata"])
        result["version"] = result["id"]
        result["parent"] = result["parents"][0] if result["parents"] else None
        return result

    def _resolve_base(self, revision):
        if revision == "HEAD":
            target = self._head()
            if target is None:
                raise GraphError("No story loaded; run ingest or init --example")
            return target
        # A movable reference must never change the meaning of an exact object ID.
        row = self.connection.execute("SELECT id FROM vcs_commits WHERE id=?", (revision,)).fetchone()
        if row:
            return row[0]
        refs = self.connection.execute("SELECT target FROM vcs_refs WHERE name IN (?,?,?)",
                                       (revision, f"refs/heads/{revision}", f"refs/tags/{revision}")).fetchall()
        if len(refs) > 1:
            raise GraphError(f"Ambiguous revision name; use refs/heads/ or refs/tags/: {revision}")
        if refs:
            if refs[0][0] is None:
                raise GraphError(f"Unborn branch: {revision}")
            return refs[0][0]
        if re.fullmatch(r"[a-f0-9]{7,64}", revision):
            matches = self.connection.execute("SELECT id FROM vcs_commits WHERE id LIKE ?", (revision + "%",)).fetchall()
            if len(matches) == 1:
                return matches[0][0]
            if len(matches) > 1:
                raise GraphError(f"Ambiguous commit prefix: {revision}")
        aliases = self.connection.execute("SELECT id FROM vcs_commits WHERE snapshot=? ORDER BY sequence", (revision,)).fetchall()
        if len(aliases) == 1:
            return aliases[0][0]
        if aliases:
            raise GraphError("Ambiguous snapshot ancestry; use a commit ID from log")
        raise GraphError(f"Unknown snapshot or revision: {revision}")

    def resolve(self, revision="HEAD"):
        if not isinstance(revision, str) or not revision:
            raise GraphError("Revision must be a nonempty string")
        match = re.fullmatch(r"([^~^]+)((?:[~^]\d*)*)", revision)
        if not match:
            raise GraphError(f"Invalid revision: {revision}")
        current = self._resolve_base(match[1])
        for operator, raw_count in re.findall(r"([~^])(\d*)", match[2]):
            count = int(raw_count or 1)
            if count > 10000:
                raise GraphError("Revision traversal exceeds 10000 steps")
            if operator == "^":
                if count == 0:
                    continue
                parents = self._commit_record(current)["parents"]
                if count > len(parents):
                    raise GraphError(f"No parent {count} for {current}")
                current = parents[count - 1]
            else:
                for _ in range(count):
                    parents = self._commit_record(current)["parents"]
                    if not parents:
                        raise GraphError(f"Revision has no earlier first parent: {revision}")
                    current = parents[0]
        return current

    def _blob(self, snapshot):
        row = self.connection.execute("SELECT document FROM snapshots WHERE id=?", (snapshot,)).fetchone()
        if row is None:
            raise GraphError(f"Unknown snapshot: {snapshot}")
        return row[0]

    def _at(self, identifier):
        record = self._commit_record(identifier)
        project = Project.model_validate_json(self._blob(record["snapshot"]))
        project.version = identifier
        return StoryGraph(project)

    def _working(self):
        state = self._state()
        if state["work"] is None:
            raise GraphError("No story loaded; run ingest or init --example")
        project = Project.model_validate_json(state["work"])
        head = self._head(state)
        clean = head and digest(encode_document(project)) == self._commit_record(head)["snapshot"]
        project.version = head if clean else "working:" + digest(encode_document(project))
        return StoryGraph(project)

    def load(self, version: str | None = None):
        if version is None:
            self._read_token = self._token()
            return self._working()
        # Content hashes remain immutable aliases even when their ancestry is ambiguous.
        if self.connection.execute("SELECT 1 FROM snapshots WHERE id=?", (version,)).fetchone():
            project = Project.model_validate_json(self._blob(version))
            project.version = version
            return StoryGraph(project)
        return self._at(self.resolve(version))

    @staticmethod
    def _validate(graph):
        errors = [f for f in graph.validate() if f.severity == "error"]
        if errors:
            raise GraphError("Invalid graph: " + "; ".join(f.message for f in errors))

    @staticmethod
    def _guard(previous, graph, authorized_locked=None):
        if previous is None:
            return
        authorized = set(authorized_locked or [])
        next_nodes = graph.nodes
        for identifier, node in previous.nodes.items():
            changed = identifier not in next_nodes or next_nodes[identifier] != node
            if node.locked and changed and identifier not in authorized:
                raise GraphError(f"Locked snapshot canon requires authorization: {identifier}")
            if (identifier in next_nodes and node.status != CanonStatus.CANON
                    and next_nodes[identifier].status == CanonStatus.CANON and identifier not in authorized):
                raise GraphError(f"Canon promotion requires authorization: {identifier}")

    def _record(self, graph, parents, message, author="human", metadata=None):
        encoded = encode_document(graph.document)
        snapshot = digest(encoded)
        created, metadata = now(), metadata or {}
        identifier = commit_id(snapshot, parents, message, author, created, metadata)
        self.connection.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?)", (snapshot, encoded))
        self.connection.execute("INSERT INTO vcs_commits(id,snapshot,parents,message,author,created,metadata) VALUES(?,?,?,?,?,?,?)",
                               (identifier, snapshot, json.dumps(parents), message, author, created, json.dumps(metadata)))
        # Keep the legacy append-only audit readable, without using it as HEAD.
        parent_snapshot = self._commit_record(parents[0])["snapshot"] if parents else None
        self.connection.execute("INSERT INTO history(version,parent,message) VALUES(?,?,?)", (snapshot, parent_snapshot, message))
        self._move_head(identifier, encoded, action="commit")
        return identifier

    def _move_head(self, target, work=None, action="checkout", detail=None):
        state, old = self._state(), self._head()
        if state["head_ref"]:
            self.connection.execute("UPDATE vcs_refs SET target=? WHERE name=?", (target, state["head_ref"]))
        else:
            self.connection.execute("UPDATE vcs_state SET detached=? WHERE singleton=1", (target,))
        if work is None and target:
            work = self._blob(self._commit_record(target)["snapshot"])
        self.connection.execute("UPDATE vcs_state SET work=?,base=?,pending=NULL,revision=revision+1 WHERE singleton=1", (work, target))
        self._reflog(action, old, target, detail)

    def _reflog(self, action, old, new, detail=None):
        self.connection.execute("INSERT INTO vcs_reflog(action,old_head,new_head,created,detail) VALUES(?,?,?,?,?)",
                               (action, old, new, now(), json.dumps(detail or {})))

    def _check_parent(self, graph, parent):
        head = self._head()
        if parent is not None:
            if str(parent).startswith("working:"):
                if self._working().document.version != parent:
                    raise GraphError("Stale working-copy parent")
                actual = head
            else:
                actual = self.resolve(parent)
            if actual != head:
                raise GraphError("Stale parent differs from HEAD; create and checkout a branch before committing")
        version = graph.document.version
        if version.startswith("working:") and version != self._working().document.version:
            raise GraphError("Stale working graph; reload before writing")
        if self.connection.execute("SELECT 1 FROM vcs_commits WHERE id=?", (version,)).fetchone() and version != head:
            raise GraphError("Stale graph is based on another commit; checkout its branch first")
        is_blob = self.connection.execute("SELECT 1 FROM snapshots WHERE id=?", (version,)).fetchone()
        if is_blob and (not head or self._commit_record(head)["snapshot"] != version):
            raise GraphError("Stale snapshot alias differs from HEAD; load the current working copy")
        if head and (version == head or is_blob) and self._working().document.version.startswith("working:"):
            raise GraphError("Stale committed graph cannot replace an uncommitted working copy; reload working state")
        return head

    def commit(self, graph, parent=None, message="", authorized_locked=None, *, author="human"):
        self._validate(graph)
        with self._write():
            if self._state()["pending"]:
                raise GraphError("Pending merge/revert: resolve conflicts and use commit_working, or abort")
            head = self._check_parent(graph, parent)
            self._guard(self._at(head) if head else None, graph, authorized_locked)
            identifier = self._record(graph, [head] if head else [], message, author)
        return identifier

    def save_working(self, graph, authorized_locked=None):
        self._validate(graph)
        with self._write():
            if self._state()["pending"]:
                raise GraphError("Pending operation; resolve or abort before saving new work")
            head = self._check_parent(graph, None)
            self._guard(self._at(head) if head else None, graph, authorized_locked)
            self.connection.execute("UPDATE vcs_state SET work=?,base=?,revision=revision+1 WHERE singleton=1",
                                   (encode_document(graph.document), head))
        return self.status()

    def status(self):
        # Observing status establishes the optimistic revision for the next write.
        # Internal callers run inside an already-guarded transaction.
        self._read_token = self._token()
        state = self._state()
        head = self._head(state)
        dirty = state["work"] is not None and (head is None or digest(state["work"]) != self._commit_record(head)["snapshot"])
        changes = self._diff_graphs(self._at(head), self._working()) if head and state["work"] else {"nodes": {}, "edges": {}, "project_fields": []}
        pending = json.loads(state["pending"]) if state["pending"] else None
        if pending:
            pending = {key: value for key, value in pending.items() if key not in {"original_work", "original_base"}}
        return {"branch": state["head_ref"][11:] if state["head_ref"] else None,
                "head": head, "detached": state["head_ref"] is None, "dirty": bool(dirty),
                "revision": state["revision"], "changes": changes,
                "pending": pending}

    @staticmethod
    def _ref_name(name, kind):
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name)
                or ".." in name or "//" in name or name.endswith(("/", ".", ".lock"))
                or any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))
                or name == "HEAD" or name.startswith("refs/")):
            raise GraphError(f"Invalid {kind} name: {name}")
        return f"refs/{kind}/{name}"

    def _refs(self, kind):
        state = self._state()
        return [{"name": row["name"][len(f'refs/{kind}/'):], "target": row["target"],
                 "current": row["name"] == state["head_ref"]}
                for row in self.connection.execute("SELECT name,target FROM vcs_refs WHERE name LIKE ? ORDER BY name", (f"refs/{kind}/%",))]

    def branches(self):
        return self._refs("heads")

    def tags(self):
        return self._refs("tags")

    def _create_ref(self, name, kind, start):
        qualified = self._ref_name(name, kind)
        with self._write():
            target = self.resolve(start or "HEAD")
            if self.connection.execute("SELECT 1 FROM vcs_refs WHERE name=?", (qualified,)).fetchone():
                raise GraphError(f"{kind} already exists: {name}")
            self.connection.execute("INSERT INTO vcs_refs VALUES(?,?)", (qualified, target))
            self._reflog("create_" + kind, self._head(), self._head(), {"ref": qualified, "target": target})
        return {"name": name, "target": target}

    def create_branch(self, name, start=None):
        return self._create_ref(name, "heads", start)

    def create_tag(self, name, target=None):
        return self._create_ref(name, "tags", target)

    def checkout(self, revision, discard_changes=False):
        with self._write():
            if self._state()["pending"]:
                raise GraphError("Pending merge/revert; commit or abort before checkout")
            if self.status()["dirty"] and not discard_changes:
                raise GraphError("Uncommitted working changes; commit them or explicitly discard changes")
            target = self.resolve(revision)
            qualified = revision if revision.startswith("refs/heads/") else f"refs/heads/{revision}"
            branch = self.connection.execute("SELECT 1 FROM vcs_refs WHERE name=?", (qualified,)).fetchone()
            if self.connection.execute("SELECT 1 FROM vcs_commits WHERE id=?", (revision,)).fetchone():
                branch = None
            old = self._head()
            self.connection.execute("UPDATE vcs_state SET head_ref=?,detached=?,work=?,base=?,revision=revision+1 WHERE singleton=1",
                                   (qualified if branch else None, None if branch else target,
                                    self._blob(self._commit_record(target)["snapshot"]), target))
            self._reflog("checkout", old, target, {"revision": revision, "discard_changes": discard_changes})
        return self.status()

    def log(self, revision="HEAD", all_branches=False, limit=100):
        if not 1 <= limit <= 10000:
            raise GraphError("Log limit must be between 1 and 10000")
        if all_branches:
            return [self._commit_record(row[0]) for row in self.connection.execute("SELECT id FROM vcs_commits ORDER BY sequence DESC LIMIT ?", (limit,))]
        head = self.resolve(revision)
        reachable, queue = set(), [head]
        while queue:
            current = queue.pop()
            if current in reachable:
                continue
            reachable.add(current)
            queue.extend(self._commit_record(current)["parents"])
        return [self._commit_record(row[0]) for row in self.connection.execute("SELECT id FROM vcs_commits ORDER BY sequence DESC") if row[0] in reachable][:limit]

    def show(self, revision="HEAD"):
        record = self._commit_record(self.resolve(revision))
        record["document"] = self._at(record["id"]).document.model_dump(mode="json")
        return record

    def history(self):
        return [self._commit_record(row[0]) for row in self.connection.execute("SELECT id FROM vcs_commits ORDER BY sequence")]

    def reflog(self, limit=100):
        """Inspect append-only HEAD/ref operations; commit IDs can be rescued as refs."""
        if not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise GraphError("Reflog limit must be between 1 and 10000")
        rows = self.connection.execute("SELECT * FROM vcs_reflog ORDER BY sequence DESC LIMIT ?", (limit,))
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]

    @staticmethod
    def _diff_graphs(left, right):
        result = {}
        for field in ("nodes", "edges"):
            a, b = getattr(left, field), getattr(right, field)
            result[field] = {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
                             "changed": sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
                             "details": {k: {"before": a[k].model_dump(mode="json") if k in a else None,
                                             "after": b[k].model_dump(mode="json") if k in b else None}
                                         for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)}}
        a, b = left.document.model_dump(mode="json"), right.document.model_dump(mode="json")
        result["project_fields"] = [k for k in a if k not in ("nodes", "edges", "version") and a[k] != b[k]]
        result["project_details"] = {k: {"before": a[k], "after": b[k]} for k in result["project_fields"]}
        return result

    def diff(self, a=None, b=None):
        if a is None:
            return self._diff_graphs(self.load("HEAD"), self._working())
        return self._diff_graphs(self.load(a), self.load(b) if b else self._working())

    # Complex merge/revert state transitions are kept separate from persistence/ref APIs.
    def commit_working(self, message, author="human", authorized_locked=None):
        from .vcs_operations import commit_working
        return commit_working(self, message, author, authorized_locked)

    def merge(self, revision, message=None, authorized_locked=None):
        from .vcs_operations import merge
        return merge(self, revision, message, authorized_locked)

    def revert(self, revision, message=None, authorized_locked=None):
        from .vcs_operations import revert
        return revert(self, revision, message, authorized_locked)

    def resolve_conflicts(self, resolutions):
        from .vcs_operations import resolve_conflicts
        return resolve_conflicts(self, resolutions)

    def abort_merge(self):
        from .vcs_operations import abort_merge
        return abort_merge(self)
