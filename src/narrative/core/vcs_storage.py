"""SQLite schema/migration and canonical blob encoding for story version control."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from .graph import GraphError

SCHEMA_VERSION = 2


def encode_document(document):
    payload = document.model_dump(mode="json") if hasattr(document, "model_dump") else dict(document)
    payload["version"] = "snapshot"
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def commit_id(snapshot, parents, message, author, created, metadata, nonce=None):
    return digest(json.dumps({"snapshot": snapshot, "parents": parents, "message": message,
                              "author": author, "created": created, "metadata": metadata,
                              "nonce": nonce if nonce is not None else uuid4().hex}, sort_keys=True))


def setup(connection: sqlite3.Connection):
    """All DDL/backfill is atomic. Legacy rows are neither updated nor removed."""
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise GraphError(f"Database schema {version} is newer than supported {SCHEMA_VERSION}")
    connection.execute("BEGIN IMMEDIATE")
    try:
        statements = [
            "CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, document TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS history (sequence INTEGER PRIMARY KEY AUTOINCREMENT, version TEXT NOT NULL REFERENCES snapshots(id), parent TEXT, message TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS vcs_commits (sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, snapshot TEXT NOT NULL REFERENCES snapshots(id), parents TEXT NOT NULL, message TEXT NOT NULL, author TEXT NOT NULL, created TEXT NOT NULL, metadata TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS vcs_refs (name TEXT PRIMARY KEY, target TEXT REFERENCES vcs_commits(id))",
            "CREATE TABLE IF NOT EXISTS vcs_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), head_ref TEXT REFERENCES vcs_refs(name), detached TEXT REFERENCES vcs_commits(id), work TEXT, base TEXT REFERENCES vcs_commits(id), revision INTEGER NOT NULL, pending TEXT)",
            "CREATE TABLE IF NOT EXISTS vcs_reflog (sequence INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, old_head TEXT, new_head TEXT, created TEXT NOT NULL, detail TEXT NOT NULL)",
        ]
        for statement in statements:
            connection.execute(statement)
        for table, reason in (("snapshots", "snapshots are immutable"), ("history", "history is append only"),
                              ("vcs_commits", "commits are immutable"), ("vcs_reflog", "reflog is append only")):
            for action in ("UPDATE", "DELETE"):
                connection.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, '{reason}'); END")
        if not connection.execute("SELECT 1 FROM vcs_state WHERE singleton=1").fetchone():
            latest = None
            prior = {}
            rows = connection.execute("SELECT sequence,version,parent,message,created FROM history ORDER BY sequence").fetchall()
            for sequence, snapshot, parent, message, created in rows:
                if not connection.execute("SELECT 1 FROM snapshots WHERE id=?", (snapshot,)).fetchone():
                    raise GraphError(f"Legacy snapshot is missing: {snapshot}")
                if parent and parent not in prior:
                    raise GraphError(f"Legacy parent has no earlier commit: {parent}")
                parents = [prior[parent][-1]] if parent else []
                metadata = {"legacy_sequence": sequence, "legacy_snapshot": snapshot,
                            "legacy_parent_resolution": "latest earlier history occurrence",
                            "legacy_parent_ambiguous": bool(parent and len(prior[parent]) > 1)}
                identifier = commit_id(snapshot, parents, message, "legacy", created, metadata, nonce=f"legacy:{sequence}")
                connection.execute("INSERT INTO vcs_commits(id,snapshot,parents,message,author,created,metadata) VALUES(?,?,?,?,?,?,?)",
                                   (identifier, snapshot, json.dumps(parents), message, "legacy", created, json.dumps(metadata)))
                prior.setdefault(snapshot, []).append(identifier)
                latest = identifier
            connection.execute("INSERT INTO vcs_refs VALUES('refs/heads/main',?)", (latest,))
            work = None if latest is None else connection.execute("SELECT document FROM snapshots WHERE id=(SELECT snapshot FROM vcs_commits WHERE id=?)", (latest,)).fetchone()[0]
            connection.execute("INSERT INTO vcs_state VALUES(1,'refs/heads/main',NULL,?,?,0,NULL)", (work, latest))
            if latest:
                connection.execute("INSERT INTO vcs_reflog(action,old_head,new_head,created,detail) VALUES('migrate',NULL,?,?,?)",
                                   (latest, now(), json.dumps({"legacy_rows": len(rows)})))
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
