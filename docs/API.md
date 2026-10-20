# API and data contract

`Node(id, kind, label, level=0, parent_id=None, status=CANON, locked=False, time=0, order=0, revelation_order=0, threads=[], attributes={}, transition=None, hard_constraints=[], soft_constraints=[], evidence=[], provenance=Provenance(), confidence=1, version=1, purpose='', duration=0, completion='draft')`.

`Edge(id, source, target, kind, weight=1, confidence=1, evidence=[], provenance=Provenance(), status=CANON, timestamp=None, version=1)`.

`Transition(requires={}, effects={}, requires_knowledge={}, knowledge_updates={}, belief_updates={}, irreversible=[], exceptions=[], participants=[], resources=[], consequences=[])`.

`State(values={}, knowledge={}, beliefs={}, irreversible=[])` uses dict[str, list[str]] knowledge/beliefs. `Constraint(id, key, expected, scope='invariant', description='')`.

`Project(title, nodes=[], edges=[], initial_state=State(), constraints=[], medium='screen', version='working', metadata={})`.

`Finding(code, message, node_ids=[], severity='error', evidence=[], confidence=1, method='deterministic')`.

Use `StoryGraph(Project)` then defensive `.document` for persistence. `.nodes`/`.edges`/`.get()` return copies. `simulate(graph) -> SimulationResult` returns `state`, `findings`, `applied`, `trace`.

CLI accepts global `--db PATH`; each action emits JSON. Use `python -m narrative --help` for exact command options. Invalid data and budget exhaustion return nonzero exits with structured errors.

The machine-readable JSON Schema is in `docs/schema.json`. `StoryGraph.constraints_for(id)` resolves project and ancestor commitments. Design values inherit implicitly when absent from a child; an explicit conflicting child annotation fails validation. Ancestor invariants are checked on descendant transitions. Hypothesis content cannot execute as CANON; represent the act of hearing testimony as a canonical observation event with belief updates, leaving the testimony itself HYPOTHETICAL.

Dependency edge direction is prerequisite/influence → dependent outcome, including `REQUIRES` (the source is required by the target). `FORESHADOWS` uses setup → payoff, whereas `PAYS_OFF` uses payoff → setup. Causal traversal does not infer causality from thematic edges.

## Local story version control

`SnapshotStore(path)` retains immutable content blobs separately from commit
identities. The following methods use commit IDs or revision expressions:

| Method | Result and behavior |
| --- | --- |
| `load(version=None)` | Defensive `StoryGraph`; omitted version reads persistent working state, explicit revision reads immutable content |
| `status()` | `branch`, `head`, `detached`, `dirty`, working `revision`, `changes`, and pending merge/revert state |
| `save_working(graph, authorized_locked=None)` | Validate and save uncommitted whole-story work; return status |
| `commit_working(message, author='human', authorized_locked=None)` | Commit saved work with nonblank message/author; reject ordinary clean work; return new commit ID |
| `commit(graph, parent=None, message='', authorized_locked=None)` | Compatibility whole-graph commit; omitted parent is current HEAD, explicit parent must match HEAD |
| `branches()` / `tags()` | Named references with short `name` and `target`; branches include `current` |
| `create_branch(name, start=None)` | Create branch at a revision or HEAD, without switching |
| `create_tag(name, target=None)` | Create an immutable tag at a revision or HEAD |
| `checkout(revision, discard_changes=False)` | Load branch with symbolic HEAD, or tag/commit with detached HEAD; return status |
| `resolve(revision='HEAD')` | Resolve branch/tag, commit or unique prefix of at least seven characters, `HEAD~N`, or `HEAD^N` |
| `log(revision='HEAD', all_branches=False, limit=100)` | Commit ancestry records with ordered parent IDs |
| `show(revision='HEAD')` | Commit metadata and the immutable story document |
| `reflog(limit=100)` | Append-only HEAD/ref operation records, newest first, with decoded detail |
| `history()` | All commits oldest first, retaining legacy `version` and `parent` fields |
| `diff(a=None, b=None)` | Zero refs: HEAD→working; one ref: revision→working; two refs: revision→revision |
| `merge(revision, message=None, authorized_locked=None)` | Up-to-date, fast-forward or two-parent merge result; persist conflicts without committing |
| `revert(revision, message=None, authorized_locked=None)` | Apply inverse first-parent delta to current HEAD while preserving unrelated later changes |
| `resolve_conflicts(resolutions)` | Map reported JSON pointer paths to `ours`, `theirs`, or `base`; stage resolved work, then explicitly commit |
| `abort_merge()` | Restore pre-operation state for pending merge or revert |
| `close()` | Close the SQLite connection |

Merge/revert/resolve/abort return dictionaries with a `status` such as `merged`,
`fast_forward`, `up_to_date`, `conflicts`, `resolved`, `aborted`, or `invalid`, and a
`committed` boolean. Conflicts include paths and base/ours/theirs values with
existence flags; missing keys and JSON null are distinct. Conflicted or invalid
CLI operations return nonzero status. Resolved conflicts remain uncommitted until
`commit -m MESSAGE`.

Working loads use `Project.version='working:<digest>'` when dirty, keeping
version-scoped evaluation ratings separate from the committed version. Use
`status()['head']` for commit ancestry, rather than assuming the working graph's
version is a commit ID. Graph locks and proposal-to-canon promotions require
explicit node authorization even during merges. Merge/revert also check forward
simulation and reject newly introduced state failures. Existing state defects
can be preserved during ordinary authoring and commits.

Mutations atomically compare the caller's loaded HEAD and working revision.
Stale writers fail instead of appending orphan commits. Legacy snapshots and
history remain intact; opening an older database performs an idempotent additive
migration. Blob-hash aliases remain readable, but ambiguous aliases cannot
define ancestry. The append-only mechanism protects application history; it is
not a security boundary against an owner replacing the SQLite file.

`core.merge.merge_documents(base, ours, theirs, resolutions=None)` is a pure
structured three-way merge. It returns `document` and `conflicts`, merges nodes
and edges by stable ID, merges mappings recursively, and treats ordered lists as
atomic values. Source documents are not mutated. See
[VERSION_CONTROL.md](VERSION_CONTROL.md) for examples and limits.
