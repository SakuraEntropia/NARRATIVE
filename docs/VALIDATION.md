# Validation — 2026-10-19

Local environment: Python 3.14.6, Pydantic 2.13.4, NetworkX 3.6.1. Editable package installation and the actual `narrative` console entry point succeeded. No paid API credentials were used.

## Executed checks

- `pytest -q`: **58 passed**. See [raw test output](../reports/test-results.txt).
- `ruff check .`: **all checks passed**. See [raw lint output](../reports/lint-results.txt).
- All required CLI commands exercised by tests, including import, simulation, proposed refinement, analyses, B1–B9, counterfactual preview, explicit approval, duel, audit, version diff and HTML/JSON export.
- A–G original-fixture experiment checks: **9/9 true**. Full evidence and measured timings: [experiments.json](../reports/experiments.json).
- Local browser checks: three-thread score rendered, node search found CLIMAX, node click revealed state requirements/knowledge/evidence, sparse attention table rendered, typed polyphony heatmap rendered, nine benchmark records displayed with unassigned model/human scores.
- HTML export escapes imported script delimiters and uses text-only DOM insertion; an injection regression test passes.

## Context and usage measurement

Experiment G repeats the same encoded setup/payoff query 5 times. Full-context baseline serialized **222,350 UTF-8 byte units**, compared with **43,929 incremental/cache units** (80.24% fewer serialized units), with **4 cache hits**. This is primarily repeat-query cache reuse on a small graph, not a claim of long-form semantic compression.

The saved run measured **0.005355 s** for the baseline versus **0.005875 s** for retrieval/cache. No speedup is claimed. Missing dependencies against the independent encoded graph oracle: **0**; query outputs matched. Restricted-budget retrieval explicitly reported overflow. This oracle cannot detect missing semantic dependencies that were never encoded.

Application demo provider usage: **0 API calls, 0 billed prompt/completion tokens, $0 API cost**. Byte estimates are not tokenizer counts. Development assistant usage is outside the application measurement. These results do not demonstrate artistic improvement or reader-experience equivalence.

## Coverage and remaining work

Deterministic core invariants, proposed/canon separation, ancestral constraints, failed-event atomicity, knowledge/irreversibility, locked snapshots, cache invalidation and budget limits have regression tests. The original fixture is AI-assisted synthetic structural test data. No external literary corpus or human panel was used.

See [implementation status and limitations](LIMITATIONS.md) for partial/unimplemented mechanisms, then [roadmap](ROADMAP.md) for priorities. Model-assisted creative generation, independent model critics, calibrated emotion/novelty judgments and multi-timeline time travel remain research work. The local HTML page is a read-only inspector.
