# NARRATIVE Implementation Plan

> For agentic workers: execute the tasks in parallel only after their contracts are fixed; run core verification before optimization or visualization.

**Goal:** An offline, reproducible graph-based story engineering vertical slice.

**Architecture:** One Pydantic Project projected to a multigraph. Deterministic simulation and isolated mutation underpin proposed refinement, analytical projections and explicit uncertain evaluation.

**Tech Stack:** Python 3.12+, Pydantic, NetworkX, SQLite, pytest, argparse, static HTML.

**Spec:** docs/SPEC.md and docs/API.md.

## Global constraints

No silent canon promotion. Locked changes need explicit IDs. No paid API in tests. Bound depth, context, retries and iteration counts. Distinguish measurable facts, proxies and unvalidated reader experience.

## Task 1: Graph core
Files: core/schema.py, graph.py, state_machine.py, versioning.py; tests/test_core.py.
- [x] Validate IDs and references; reject parent cycles while allowing symbolic contradictions.
- [x] Test knowledge gating, atomic failed events, irreversible changes and chronology independent from presentation.
- [x] Test immutable snapshot reload/diff and locked-canon authorization.
- [x] Run `pytest tests/test_core.py` before integrating optimization.

## Task 2: Analysis/evaluation
Files: analysis/*, evaluation/*; tests/test_analysis.py.
- [x] Implement sparse typed attention and named descriptive diagnostics, including setup/payoff and intentional sparsity.
- [x] Implement horizontal thread trajectories and vertical typed relations with evidence.
- [x] Return B1–B9 records with null uncalibrated judgments, safeguards, human calibration and weight sensitivity.
- [x] Test three independent voices and worldbuilding complexity without automatic reward.

## Task 3: Refinement/memory/providers
Files: refinement.py, memory.py, providers.py; tests/test_memory_refinement.py.
- [x] Build structured-output validation with finite retries and visibly deterministic mock templates.
- [x] Bound recursion; inherit hard constraints; return checkpoints and upward feedback proposals.
- [x] Retrieve mandatory constraints plus causal/knowledge/long-range neighbors under explicit context limits.
- [x] Test dependency-aware cache reuse/invalidation and project/iteration operation telemetry.

## Task 4: Revision/experiments
Files: optimization.py, examples/*, experiments.py; tests/test_optimization.py.
- [x] Trace upstream influence with causal types distinguished from thematic links.
- [x] Generate multiple controlled pivots; simulate deep-copied branches; prioritize hard validity.
- [x] Produce evidence-based critic disagreements and Pareto comparisons, retain first-time/expert perspectives.
- [x] Run experiments A–G with measured counters and correctness comparisons.

## Task 5: Public delivery
Files: cli.py, visualization.py, README.md, pyproject.toml, CI workflow.
- [x] Exercise all CLI commands in temporary databases.
- [x] Export computed inspection data to escaped self-contained HTML.
- [x] Run full tests/lint, save actual execution and cost reports, document partial/unvalidated features.
- [x] Initialize isolated Git repository, create public GitHub repository and push only project files; verify remote commit.
