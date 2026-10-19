"""Content-addressed immutable snapshots with append-only SQLite history."""

import hashlib
import json
import sqlite3
from pathlib import Path

from .graph import GraphError, StoryGraph
from .schema import CanonStatus, Project


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
          version TEXT NOT NULL REFERENCES snapshots(id), parent TEXT, message TEXT NOT NULL,
          created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
          BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
          BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON history
          BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
        CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON history
          BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
        """)

    def close(self):
        self.connection.close()

    def commit(self, graph: StoryGraph, parent: str | None = None, message: str = "",
               authorized_locked: list[str] | None = None) -> str:
        errors = [f for f in graph.validate() if f.severity == "error"]
        if errors:
            raise GraphError("Invalid graph: " + "; ".join(f.message for f in errors))
        if parent is None:
            latest = self.connection.execute("SELECT version FROM history ORDER BY sequence DESC LIMIT 1").fetchone()
            parent = latest[0] if latest else None
        if parent:
            previous = self.load(parent)
            authorized = set(authorized_locked or [])
            for node_id, node in previous.nodes.items():
                changed = node_id not in graph.nodes or graph.get(node_id) != node
                if node.locked and changed and node_id not in authorized:
                    raise GraphError(f"Locked snapshot canon requires authorization: {node_id}")
                if (node_id in graph.nodes and node.status != CanonStatus.CANON
                        and graph.get(node_id).status == CanonStatus.CANON and node_id not in authorized):
                    raise GraphError(f"Canon promotion requires authorization: {node_id}")
        document = graph.document.model_dump(mode="json")
        document["version"] = "snapshot"
        encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        version = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?)", (version, encoded))
            self.connection.execute("INSERT INTO history(version,parent,message) VALUES (?,?,?)", (version, parent, message))
        return version

    def load(self, version: str | None = None) -> StoryGraph:
        if version is None:
            row = self.connection.execute("SELECT version FROM history ORDER BY sequence DESC LIMIT 1").fetchone()
            if not row:
                raise GraphError("No story loaded; run ingest or init --example")
            version = row[0]
        row = self.connection.execute("SELECT document FROM snapshots WHERE id = ?", (version,)).fetchone()
        if not row:
            raise GraphError(f"Unknown snapshot: {version}")
        project = Project.model_validate_json(row[0])
        project.version = version
        return StoryGraph(project)

    def history(self) -> list[dict]:
        cursor = self.connection.execute("SELECT sequence,version,parent,message,created FROM history ORDER BY sequence")
        return [dict(zip(("sequence", "version", "parent", "message", "created"), row)) for row in cursor]

    def diff(self, a: str, b: str) -> dict:
        left, right = self.load(a), self.load(b)
        result = {}
        for field in ("nodes", "edges"):
            aa, bb = getattr(left, field), getattr(right, field)
            result[field] = {"added": sorted(bb.keys() - aa.keys()), "removed": sorted(aa.keys() - bb.keys()),
                             "changed": sorted(k for k in aa.keys() & bb.keys() if aa[k] != bb[k])}
        da, db = left.document.model_dump(mode="json"), right.document.model_dump(mode="json")
        result["project_fields"] = [k for k in da if k not in ("nodes", "edges", "version") and da[k] != db[k]]
        return result
