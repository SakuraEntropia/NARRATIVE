# NARRATIVE

A local, versioned story engineering harness. Stories are typed graphs with chronological state transitions, independent presentation order, explicit knowledge, evidence and proposed revisions.

This is an executable research foundation. Structural measurements, heuristic proxies and subjective reader judgments are separate. Offline runs do not invent model scores or claim proven artistic improvement.

## Features

- Typed multigraph, atomic world/character/knowledge transitions and immutable SQLite snapshots.
- Bounded recursive proposed refinement with inherited constraints.
- Sparse typed Story Attention, three-thread polyphony and evidence-bearing B1–B9 reports.
- Backward dependency search, isolated counterfactual pivots and adversarial comparison.
- Context budgets, dependent cache invalidation and honest usage telemetry.
- CLI, original fixtures, reproducible experiments and self-contained HTML inspector.

## Installation

Python 3.12 or later:

```bash
python -m pip install -e '.[dev]'
```

No API key is required. The default provider is an explicitly labeled deterministic template provider. External model integration is an extension point; no hosted LLM is bundled.

## Quick start

```bash
narrative --db demo.db init --example
narrative --db demo.db compile
narrative --db demo.db analyze --attention --polyphony
narrative --db demo.db evaluate --benchmark all
narrative --db demo.db refine --node ACT_1 --depth 2
narrative --db demo.db pivot --target CLIMAX
narrative --db demo.db duel --candidates 3
narrative --db demo.db audit
narrative --db demo.db history
narrative --db demo.db export --format html --output story.html
narrative experiments --output experiments.json
```

Every command emits JSON. Use a new database per project. Import another original fixture with `narrative --db defective.db ingest examples/weak_motivation.json`. `narrative diff VERSION_A VERSION_B` compares immutable full snapshot IDs from `history`.

Refinement saves PROPOSED children; it never promotes them. Pivot reports are previews by default. Explicitly approve a selected proposal with `pivot --target CLIMAX --candidate 0 --approve`; locked node changes additionally need `--authorize-locked NODE_ID`. Counterfactual preview simulation is labeled hypothetical. Inspect the report before approval.

## Architecture

One Pydantic Project is the source of truth. NetworkX, analysis, timeline and HTML are projections; SQLite stores immutable content-addressed snapshots. See [architecture](docs/ARCHITECTURE.md), [data/API contract](docs/API.md), [specification](docs/SPEC.md) and [roadmap](docs/ROADMAP.md).

The original fixture, *The Last Tide Ledger*, has three incompatible civic duties, an important secret, a distant fuse setup/payoff, and an irreversible climactic choice. Alternative fixtures weaken motivation and add unused worldbuilding. These are authored structural test cases, not a literary reference corpus.

## Development

```bash
pytest
ruff check .
python -m narrative --help
```

See [development](docs/DEVELOPMENT.md). Measurements and actual execution results are recorded in [validation](docs/VALIDATION.md). UTF-8 context units are estimates, never billed tokens. Mock calls have zero billed API usage. Human reader calibration, corpus-relative novelty and demonstrated artistic gains remain research work.

## License

MIT. See [LICENSE](LICENSE).
