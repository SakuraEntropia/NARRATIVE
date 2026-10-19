# Backward influence and controlled revision

`backward_influence(graph, target, max_depth=8)` follows canonical, evidenced
CAUSES, REQUIRES, ENABLES, MOTIVATES, CONSTRAINS, REVEALS, KNOWS, and TRANSFORMS
relations. The function also projects earlier transition writers that supply an
explicit state or character-knowledge prerequisite. These derived records do not
become canonical edges. They identify possible providers; simulation determines
whether events actually succeed. Rank is declared edge weight × confidence /
distance, or endpoint confidence / distance for transition dependencies. It is a
search priority, not a probability of literary causation.

Symbolic, contrasting, contradictory, and setup/payoff links remain visible in a
separate association collection. An unsupported causal label is reported without
being followed. Search depth is bounded to 0–100. The original graph is never
modified by analysis.

`propose_pivots(graph, target, max_candidates=3)` selects explicit
`attributes.repair_candidates` from the target and its upstream neighborhood.
The supplied fixture contains two original authored motivation repairs. They are
validated, evidence-bearing candidates rather than output from a creative LLM.
Absent authored candidates produce an empty list. The offline provider does not
pretend to invent a repair for every possible defect.

```python
from narrative.examples import example_graph
from narrative.optimization import propose_pivots, evaluate_pivot

story = example_graph("weak_motivation")
pivot = propose_pivots(story, "CLIMAX")[0]
outcome = evaluate_pivot(story, pivot)
branch, report = outcome["branch"], outcome["report"]
assert branch.get("CLIMAX").status == "PROPOSED"
assert report["canonical_approval"] is False
```

Each `Pivot` records its ID, target, edited node, changes, node evidence IDs,
confidence, provenance, version, and declared revision cost. Permitted edits are
attributes, transition, label, purpose, chronology/presentation/revelation order,
duration, and thread membership. Dotted paths support nested attribute mappings.
To change a flat state key containing periods, replace the complete transition
mapping rather than interpreting periods in that key as a nesting convention.
Pydantic validates the resulting node.

`evaluate_pivot` deep-copies the graph. By default its edited node remains
PROPOSED. It makes another ephemeral copy in which that edit executes as canon
solely for counterfactual simulation and criticism. The report explicitly labels
this scope. The caller can request an approved isolated branch with
`approve=True`; locked node changes additionally require that exact ID in
`authorized_locked`. Original graph and snapshots remain untouched. The CLI
commits an approved branch only after a successful hard validation gate.

The report contains the detected structural proxy defect and evidence, candidate
upstream causes, proposed mutation, dependency closure, observed proxy changes,
new simulation failures, uncertainty and risk notes, declared revision cost,
zero actual model usage, nine-dimension diagnostics, and critic perspectives.
Restoring a missing motivation annotation removes an annotation defect; it does
not establish that readers experience a more convincing choice.

`affected_nodes` follows dependency edges and actual transition key/knowledge
use. A full chronological simulation accompanies local closure to expose missed
state prerequisites. Unrepresented semantic dependencies can still escape both.

`duel` evaluates a finite candidate pool once, bounded by candidate and iteration
limits, and stops for author approval. It does not autonomously accept winners or
regenerate prose. `pareto_select` excludes hard-invalid branches, then retains
nondominated structural-error, unsupported-choice, and revision-cost vectors.
These objectives remain separate. Subjective artistic quality is not assigned a
scalar or silently optimized. Further search, node insertion/deletion/merging,
independent evaluator models, and human preference acquisition remain extension
work rather than implemented research results.
