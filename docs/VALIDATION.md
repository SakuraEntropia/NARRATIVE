# Validation — 2026-10-19

Local environment: Python 3.14.6, Pydantic 2.13.4, NetworkX 3.6.1. Editable package installation and the actual `narrative` console entry point succeeded. No paid API credentials were used.

## Executed checks

- `pytest -q`: **58 passed**. See [raw test output](../reports/test-results.txt).
- `ruff check .`: **all checks passed**. See [raw lint output](../reports/lint-results.txt).
- All required CLI commands exercised by tests, including import, simulation, proposed refinement, analyses, B1–B9, counterfactual preview, explicit approval, duel, audit, version diff and HTML/JSON export.
- A–G original-fixture experiment checks: **9/9 true**. Full evidence and measured timings: [experiments.json](../reports/experiments.json).
- Local browser checks: three-thread score rendered, node search found CLIMAX, node click revealed state requirements/knowledge/evidence, sparse attention table and selectable foreshadowing matrix rendered, typed polyphony heatmap rendered, nine benchmark records displayed with unassigned model/human scores.
- HTML export escapes imported script delimiters and uses text-only DOM insertion; an injection regression test passes.

## Context and usage measurement

Experiment G repeats the same encoded setup/payoff query 5 times. Full-context baseline serialized **222,350 UTF-8 byte units**, compared with **43,929 incremental/cache units** (80.24% fewer serialized units), with **4 cache hits**. This is primarily repeat-query cache reuse on a small graph, not a claim of long-form semantic compression.

The saved run measured **0.005355 s** for the baseline versus **0.005875 s** for retrieval/cache. No speedup is claimed. Missing dependencies against the independent encoded graph oracle: **0**; query outputs matched. Restricted-budget retrieval explicitly reported overflow. This oracle cannot detect missing semantic dependencies that were never encoded.

Application demo provider usage: **0 API calls, 0 billed prompt/completion tokens, $0 API cost**. Byte estimates are not tokenizer counts. Development assistant usage is outside the application measurement. These results do not demonstrate artistic improvement or reader-experience equivalence.

## Coverage and remaining work

Deterministic core invariants, proposed/canon separation, ancestral constraints, failed-event atomicity, knowledge/irreversibility, locked snapshots, cache invalidation and budget limits have regression tests. The original fixture is AI-assisted synthetic structural test data. No external literary corpus or human panel was used.

See [implementation status and limitations](LIMITATIONS.md) for partial/unimplemented mechanisms, then [roadmap](ROADMAP.md) for priorities. Model-assisted creative generation, independent model critics, calibrated emotion/novelty judgments and multi-timeline time travel remain research work. The local HTML page is a read-only inspector.

Published project: [SakuraEntropia/NARRATIVE](https://github.com/SakuraEntropia/NARRATIVE), public `main` branch. CI runs Python 3.12, 3.13 and 3.14; the local execution above is the recorded Python 3.14 result.

## Story version control — 2026-10-20 / v0.2.0

- Installed package and Python module both report **0.2.0**. The existing Python dependencies are unchanged.
- Full deterministic suite: **141 passed**. See [version-control test output](../reports/version-control-tests.txt); [lint output](../reports/version-control-lint.txt) reports all checks passed.
- Preserved all original graph, simulation, refinement, analysis, optimization and CLI tests. A–G was rerun separately: **9/9 checks true**.
- Added pure three-way merge tests, real v1 database migration including repeated content, immutable commit identity, branch/tag/HEAD isolation, detached rescue, pending conflict persistence/abort, inverse revert, full graph/state validation, lock/promotion authorization and stale-write regressions.
- Independent review found and fixed movable refs shadowing immutable commit IDs, stale blob aliases overwriting current content, and refreshed connection state incorrectly legitimizing stale draft sources. Status observation also establishes the optimistic revision used by subsequent writes.
- Actual installed console demonstration: **37 commands**, **8 commits**, **8/8 workflow checks**, and **22 valid canonical transitions**. It exercised two-parent merging, conflict staging and explicit commit, history-preserving revert, tags, detached checkout, branch restoration and reflog. Full results and command arguments: [version-control-demo.json](../reports/version-control-demo.json). The database was temporary; no private user story was used.
- Migration leaves the original snapshots/history rows and triggers intact. Dirty checkout, unauthorized canon changes, unresolved commits and invalid merge/revert results are rejected without moving HEAD or silently dropping the saved work.
- Application API/model calls for version-control operations: **0**. No remote story synchronization, subset staging, semantic prose merge, multiple-base recursive merge, root/merge-commit revert or `HEAD@{N}` selectors are implemented. See [version-control guide](VERSION_CONTROL.md) for the supported recovery paths and exact limits.
