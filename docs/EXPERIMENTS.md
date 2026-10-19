# Reproducible experiments

Run `narrative experiments --output reports/experiments.json`. The command
computes all seven experiments afresh and saves their evidence-bearing results.
The Python equivalent is `narrative.experiments.run_experiments()`; an optional
`output_dir` writes `experiments.json` in that directory. All runs are offline.

The original synthetic dataset, **The Last Tide Ledger**, follows three distinct
threads: Mara preserves witness testimony; Ivo prepares a manual floodgate; Sera
tries to preserve civic continuity without admitting a falsified model. Their
interests conflict and converge. An opening ceramic fuse foreshadows the final
gate firing across twelve interleaved scenes. The climax preserves the district
while irreversibly consuming the fuse and exposing Mara's identity. A separate
hypothetical witness claim does not alter actual state.

`examples/original.json` is consistent under the represented rules.
`weak_motivation.json` removes the climax's stated motivation and incoming
MOTIVATES relation. `complex_low_agency.json` adds 24 unused rules and removes
participant-driven agency from decisions. These controlled variants are
mechanism tests, not independently judged fiction.

| Experiment | Computation and evidence | Scope of conclusion |
| --- | --- | --- |
| A | Two bounded refinement levels; child constraint IDs, statuses, checkpoints and telemetry | Deterministic template proposals inherit the specified parent commitment; creative usefulness is unmeasured |
| B | Detect missing motivation, trace graph and knowledge prerequisites, evaluate two authored repairs on private branches | Missing annotation evidence can be restored without canonical mutation; felt emotional improvement is unmeasured |
| C | Full thread timelines and typed relations, then remove Sera's exclusive nodes | Her accountability perspective and signed-correction prerequisite disappear; the system does not assign a quality reward to thread count |
| D | Compare agency safeguards, unused setting elements and all nine benchmark records | More ornamental worldbuilding does not automatically produce a higher score; artistic preference remains null |
| E | Retrieve PAYOFF's distant FUSE_IMAGE endpoint and measure intervening narrative nodes | An explicitly encoded long-range dependency can be retrieved without submitting the full project |
| F | Change the early manual-gate rule to false, then resimulate | The engine reports future preconditions and the preparation scene's local invariant failure |
| G | Repeat an explicit setup/payoff endpoint query five times with full context versus retrieval/cache; compare exact query outputs and an independent dependency oracle | Context units and cache behavior are measured; neither semantic equivalence nor artistic improvement is established |

G estimates context volume as UTF-8 JSON bytes, explicitly **not billed model
tokens**. The full baseline serializes the complete project on each request.
The incremental path retrieves once and serves four repeated queries from the
dependency cache. The equality check concerns explicit setup/payoff endpoints,
not complete benchmark or reader-judgment equivalence. Its dependency oracle
independently walks all encoded prerequisite relations without retrieval bounds.
The report includes the oracle, any omitted nodes, a missed-dependency rate,
actual timings, and a deliberately insufficient budget's explicit overflow.

The reports also demonstrate changed-rule cache invalidation and survival of an
unrelated cache entry. A retrieval regression discovered during development
omitted Sera's motivational predecessor chain; character and knowledge
prerequisite traversal was corrected and is now tested. This illustrates why an
independent oracle and full audits remain necessary. Zero omissions on this one
fixture do not establish a general missed-dependency rate.

For this small graph, retrieval can take longer than serializing the full
document. The measured latency fields should be consulted directly; the project
claims no latency speedup. Actual prompt tokens, completion tokens, API calls,
and API cost are all zero because no paid or external model runs. All subjective
reader-response and artistic judgments remain uncalibrated and unscored.
