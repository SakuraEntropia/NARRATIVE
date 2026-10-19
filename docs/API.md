# API and data contract

`Node(id, kind, label, level=0, parent_id=None, status=CANON, locked=False, time=0, order=0, revelation_order=0, threads=[], attributes={}, transition=None, hard_constraints=[], soft_constraints=[], evidence=[], provenance=Provenance(), confidence=1, version=1, purpose='', duration=0, completion='draft')`.

`Edge(id, source, target, kind, weight=1, confidence=1, evidence=[], provenance=Provenance(), status=CANON, timestamp=None, version=1)`.

`Transition(requires={}, effects={}, requires_knowledge={}, knowledge_updates={}, belief_updates={}, irreversible=[], exceptions=[], participants=[], resources=[], consequences=[])`.

`State(values={}, knowledge={}, beliefs={}, irreversible=[])` uses dict[str, list[str]] knowledge/beliefs. `Constraint(id, key, expected, scope='invariant', description='')`.

`Project(title, nodes=[], edges=[], initial_state=State(), constraints=[], medium='screen', version='working', metadata={})`.

`Finding(code, message, node_ids=[], severity='error', evidence=[], confidence=1, method='deterministic')`.

Use `StoryGraph(Project)` then defensive `.document` for persistence. `.nodes`/`.edges`/`.get()` return copies. `simulate(graph) -> SimulationResult` returns `state`, `findings`, `applied`, `trace`. `SnapshotStore(path).commit(graph, parent=None, message='', authorized_locked=[]) -> str`; `.load(version=None) -> StoryGraph`; `.diff(a,b) -> dict`; `.history() -> list[dict]`.

CLI accepts global `--db PATH`; each action emits JSON. Use `python -m narrative --help` for exact command options. Invalid data and budget exhaustion return nonzero exits with structured errors.

The machine-readable JSON Schema is in `docs/schema.json`. `StoryGraph.constraints_for(id)` resolves project and ancestor commitments. Design values inherit implicitly when absent from a child; an explicit conflicting child annotation fails validation. Ancestor invariants are checked on descendant transitions. Hypothesis content cannot execute as CANON; represent the act of hearing testimony as a canonical observation event with belief updates, leaving the testimony itself HYPOTHETICAL.

Dependency edge direction is prerequisite/influence → dependent outcome, including `REQUIRES` (the source is required by the target). `FORESHADOWS` uses setup → payoff, whereas `PAYS_OFF` uses payoff → setup. Causal traversal does not infer causality from thematic edges.

SQLite commits use the latest history entry when the parent is omitted, preserving lock checks. Explicit parents create branches; history and snapshots remain immutable. The append-only mechanism is application-level protection, not a security boundary against an owner replacing the database file.
