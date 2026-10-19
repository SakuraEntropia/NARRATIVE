# Bounded refinement and graph memory

The canonical document remains a `Project`. Refinement returns a cloned
`StoryGraph`; all new nodes and hierarchy edges have `PROPOSED` status. Their
transitions cannot execute in canonical simulation. Feedback names the parent
node and records `applied: false`; it never rewrites an ancestor. Retrieval
preserves every node's status, provenance, evidence, and uncertainty. A proposed
or hypothetical record in retrieved context is not an established world fact.

## Refinement contract

`refine(graph, node_id, depth=2, max_nodes=12, min_information_gain=.05,
provider=None, budget=None, token_budget=12000, max_retries=1)` returns a
`RefinementResult` containing `graph`, child IDs, checkpoints, feedback,
telemetry, and an explicit stop reason. Its JSON form includes the resulting
document. The original graph is untouched, including on failure.

The engine inherits project constraints and all ancestor hard constraints.
Conflicting definitions fail clearly. Design constraint values populate child
attributes and cannot be overridden by generated output. An explicit generated
effect that contradicts an invariant is rejected. Each parent decomposition is
installed atomically after schema, hierarchy, participant-reference and
constraint checks. This is a local proposal validation, not proof that an entire
story is semantically or artistically sound. Canonical simulation and human
approval remain separate.

Each call receives bounded graph context and a strict Pydantic output schema:
one to sixteen children with label, type, purpose, JSON attributes and optional
transition; a declared information-gain estimate; feedback; and uncertainty.
Depth, node count, per-call context, provider calls, output size and declared
information gain stop further decomposition. Checkpoints report rejected output,
context overflow and exhausted budgets. Critical scenes, thematic pivots, major
revelations and irreversible transitions receive scheduling priority and up to
four template slots instead of two. This transparent allocation heuristic is
not a quality score. A small node budget may truncate siblings; the checkpoint
records that fact.

The offline provider produces structural template slots marked
`requires_authoring`. It invents no demonstrated literary improvement. Its
information-gain number is a fixed scheduling heuristic. The engine never
reports that estimate as a measured artistic benefit.

## Retrieval contract

`retrieve(graph, targets, token_budget=12000, max_nodes=64, max_hops=8)` returns
node IDs and complete node records, connecting edge records, hard constraints,
relevant initial state, omitted IDs, warnings and telemetry. Direct targets,
causal predecessors, explicit rule/character/knowledge references, original
evidence references and setup/payoff endpoints are required evidence. Global
rules marked `attributes.global=true` are included. Global and relevant ancestor
hard constraints are retained independently of node ranking, with source status.

Attribute reference fields are `world_rules`, `rules`, `required_rules`,
`characters`, `character_ids`, `character_id`, `evidence_nodes`, `knowledge_nodes`,
`source_nodes` and `summary_of`; each may contain an ID or list of IDs. Evidence
records may also link originals through `node_id`. Summaries remain ordinary
status-bearing nodes and cannot substitute for these linked originals.

The walk follows causal upstream and required evidence links up to the traversal
bounds. Optional neighbors and ancestors fill remaining space by a documented
structural priority. Required evidence that cannot fit or a traversal that
cannot finish produces `overflow=true`, including warnings and omitted IDs.
The caller must increase the budget or change the task before model submission.
Refinement enforces this rule. The result never silently declares an incomplete
required context sufficient. Retrieval node output is capped by `max_nodes`;
mandatory constraint records can themselves exceed a small byte budget and
therefore cause explicit overflow.

Initial state is the original project state, filtered to relevant state keys and
character/audience knowledge or belief ledgers. It is not a fabricated state at
the target's time. Selected original transitions supply upstream evidence;
chronological simulation must establish the actual state when that matters.

## Budgets and telemetry

`Budget` tracks context byte units, output byte units, provider calls and known
API cost. Set `operation.parent=iteration` and `iteration.parent=project` for
three scopes. A reservation checks every scope before changing any counter.
An unknown live API cost cannot pass a hard monetary cap, so the call is stopped
before submission. No vendor credentials are serialized. `CallableProvider`
accepts an explicitly configured adapter; the package has no implicit live API.

The context estimate is the UTF-8 length of compact JSON, a conservative byte-unit
estimate rather than a tokenizer measurement. `ContextResult.estimated_tokens`
is a compatibility field with that method stated in its JSON output; new
telemetry uses `estimated_context_units` and `estimated_output_units`. Billed
`prompt_tokens`, `completion_tokens`, and API cost come only from provider usage.
They are zero for the offline mock and null for unknown live usage. If any live
call lacks usage, the corresponding aggregate stays null instead of presenting
a partial total as complete. Latency is measured wall-clock time. Iteration,
retrieved nodes, affected nodes, cache hits, calls and retries are separate fields.

Structured output is size-bounded and Pydantic-validated on every attempt. One
retry is the default, and three retries is the absolute accepted maximum. Invalid
responses consume their actual call/output reservations. No unbounded recursive
model calls occur. Output size accounting happens after the adapter returns;
external adapters should additionally enforce their provider's output-token cap.

## Cache invalidation and limits

`DependencyCache.set(key, value, dependencies)` stores defensive copies. A local
`invalidate(changed_ids, graph)` removes entries depending on the outgoing graph
closure, changed edge endpoints and ancestor summaries. Entries in unrelated
regions remain available. Score, summary, transition and consistency results can
all use this cache by declaring their evidence dependencies. Changes must be
invalidated explicitly; a cache hit is not an automatic proof of freshness.
`full_audit=true` clears every entry for recomputation, catching dependencies
missed by local declarations. It does not claim to discover unknown semantic
dependencies by itself.

The implementation builds adjacency in O(V+E), then bounds expansion and context
size. Graph accessors and proposal branches copy records, so this release targets
local graphs with hundreds or thousands of nodes. It makes no production-scale
memory, accuracy or artistic quality claim. Undeclared narrative dependencies,
provider mistakes and incomplete symbolic state models remain material limits.
