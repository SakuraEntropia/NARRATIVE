# Functional specification

## Scope and assumptions

Build the smallest rigorous foundation in Python 3.12+. One JSON/Pydantic document is canonical; graph, timeline, sparse attention and HTML are projections. SQLite stores immutable snapshots and an append-only history. All model inferences remain PROPOSED unless explicitly approved. Locked canon changes require explicit node authorization. Tests and the demo must run offline.

| ID | Input → output | Acceptance |
|---|---|---|
| FR01 Import | story JSON → typed graph snapshot | Invalid references and hierarchy cycles fail clearly |
| FR02 Simulation | state + canonical chronological events → state/findings | Atomic preconditions, knowledge and irreversible effects checked |
| FR03 Refinement | node + depth/budget → proposed children/checkpoints | Inherit constraints, bound recursion, never promote canon |
| FR04 Attention | graph → sparse typed entries and diagnostics | Long-range setup/payoff preserved; density is descriptive |
| FR05 Polyphony | graph → timelines and typed cross-thread relations | Three voices; independence and dissonance aren't mere thread count |
| FR06 Backward search | defect → ranked upstream dependencies | Symbolic links aren't causal evidence |
| FR07 Pivots | proposals → isolated validated branches | Original untouched; hard constraints take precedence |
| FR08 Regression | early change → affected closure and simulation | Broken future prerequisites reported |
| FR09 Benchmark | graph → B1–B9 evidence-bearing records | Structural, proxy and subjective results separated |
| FR10 Duel | candidates → evidence-based critiques and Pareto set | Independent reader perspectives and disagreement retained |
| FR11 Offline | deterministic provider → reproducible test run | No API key or external service required |
| FR12 Memory | bounded retrieval + cache → telemetry | Hard constraints mandatory; overflow explicit; dependent invalidation |
| FR13 CLI | init/ingest/compile/refine/analyze/evaluate/pivot/duel/audit/diff/export | JSON output, actionable errors and nonzero invalid exits |
| FR14 Experiments | original fixture → A–G reports | Measured latency/estimated context units, failures and limitations |
| FR15 Honesty | every estimate → method/evidence/uncertainty | No fabricated model scores or claims of validated artistic improvement |

## Nonfunctional requirements

No executable imported content. Structured provider output validation and finite retries. No credentials persisted. Hard budget exhaustion fails safely or returns explicitly partial work. Node IDs stable within a project. Independent graph branches use deep copies. Runtime O(V+E) for ordinary audits, bounded neighborhood traversal for retrieval. This release targets local graphs in the hundreds/thousands of nodes; no production-scale performance claim.
