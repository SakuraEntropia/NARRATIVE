# Story Attention, information and polyphony

These modules inspect the canonical graph. They neither create a second canon nor
modify the input. Only `CANON` nodes and edges with canonical endpoints enter the
projections. A graph relation is evidence of an author's declared relationship;
it is not an independent demonstration of reader response or causality.

## Sparse typed attention

`narrative.analysis.attention.analyze_attention(graph)` returns seven coordinate
lists under `sparse_matrices`. Each entry contains source/target IDs, edge ID,
edge kind, declared confidence, evidence references and strength. The calculation
is `max(0, edge.weight) * edge.confidence`. No dense N×N array is constructed.
An edge may occur in more than one interpretive projection but counts only once
in global dependency measurements.

| Projection | Encoded relations |
| --- | --- |
| Causal | CAUSES, REQUIRES, ENABLES, CONSTRAINS |
| Character | MOTIVATES, TRANSFORMS, BELONGS_TO |
| Thematic | SYMBOLIZES, PARALLELS, CONTRASTS, CONTRADICTS |
| Foreshadowing | FORESHADOWS, PAYS_OFF |
| Emotional | MOTIVATES/TRANSFORMS with endpoint `emotion` or `emotional_target` annotation |
| Visual | SYMBOLIZES with endpoint `visual_intent` or `visual` annotation |
| Knowledge/revelation | REVEALS, KNOWS, BELIEVES, OBSERVES |

The emotional and visual annotations authorize an analytical projection, not a
claim about successful emotion or imagery. Proximity, thematic similarity,
PARALLELS and SYMBOLIZES never manufacture CAUSES edges.

The ten mandatory diagnostics have explicit definitions:

1. **Attention concentration:** Herfindahl concentration of incident strength
   across nodes. Endpoints each receive the edge's strength once. Undefined on
   a graph without nonzero strengths. No target concentration is preferred.
2. **Narrative dependency density:** distinct directed attention pairs divided
   by `N(N−1)`, excluding self-loops. A graph with fewer than two nodes has
   density zero and undefined sparsity.
3. **Sparse/dense structure:** occupancy and one minus occupancy. Density is
   descriptive; neither dense nor sparse writing is automatically better.
4. **Attention continuity:** the fraction of adjacent presentation-order
   narrative components joined directly by an attention relation. Components
   include acts through scenes, events, decisions, revelations and setups/payoffs;
   equal orders use the node ID as a reproducible tie breaker. Hierarchy and
   simultaneous scenes can therefore lower this proxy without incoherence.
5. **Setup/payoff connectivity:** FORESHADOWS runs **setup → payoff**; PAYS_OFF
   runs **payoff → setup**. Either connects an explicit Foreshadowing node.
   Nonforward FORESHADOWS edges are reported for inspection, including deliberate
   nonlinear presentation. Connectivity does not establish fair setup.
6. **Attention drift:** one minus Jaccard similarity of adjacent component
   neighborhoods. Two empty neighborhoods produce null. An intentional scene
   cut can have a high change value.
7. **Redundant attention:** identical source/target/type parallel edges.
   Independent evidence can justify these edges; they are not automatically
   duplicates to delete.
8. **Orphaned narrative nodes:** no incident attention relation. All canonical
   component kinds are considered. `intentional_sparsity: true` is retained.
9. **Underdeveloped high-dependency nodes:** at least three distinct neighbors,
   unfinished completion annotation, no transition and no narrative purpose.
   This is a review threshold, not a research-calibrated defect classifier.
10. **Overloaded nodes:** distinct degree at least
    `max(5, ceil(.3 * (N−1)))`. This is also a review threshold.

Evidence lists contain graph record IDs and the source references of supplied
`Evidence` records. Original excerpts, provenance, confidence and version remain
in the canonical graph; summaries do not replace them. Edges without source
evidence are visible under `unsupported_edge_annotations`.

## Independent information ledgers

`narrative.analysis.information_masking.analyze_information(graph)` keeps:

- Author-known canon Facts, Rules and WorldState IDs.
- Character knowledge from **successfully applied** state-machine trace entries,
  ordered by diegetic time and the simulator's ID tie breaker. Failed events do
  not disclose secrets. BELIEVES and hypothetical testimony never grant knowledge.
- Audience information in revelation order, independent of chronology.

`attributes.audience_knows` accepts a fact ID, a list of fact IDs, or a boolean.
On a node, true introduces that node's ID and false discloses nothing. Other
types and lists containing nonstrings raise `ValueError`. Initial audience
knowledge can be supplied as `metadata.audience_initial_knowledge` (ID or list).
REVEALS edges introduce the target at the source's revelation order. If an
executable source event fails, its REVEALS edges are withheld and reported under
`unexecuted_revelations`; explicit audience annotations still describe what is
presented. This is a declaration of presentation, not an inference of what every
reader actually understands. A globally invalid graph can prevent simulation.

`analyze_debt(graph)` reports explicit `attributes.unresolved_debt` and unconnected
Foreshadowing nodes. `intentional_open_end: true` preserves an obligation while
excluding it from the unintentional count. This is encoding coverage, not an
assessment of satisfying closure.

## Horizontal voices and vertical relations

`narrative.analysis.polyphony.analyze_polyphony(graph)` uses `node.threads` as
declared memberships. Thread count never becomes a quality score.

`thread_timeline` follows each thread through presentation order, retaining
diegetic and revelation order separately. It exposes declared motivation,
emotion, value conflict, theme progression, transition knowledge updates,
motifs, tension and purpose. Knowledge updates here are event declarations;
the information ledger is authoritative for actual execution.

Use node attributes `motivation`, `emotion`/`emotional_target`, `value_conflict`,
`theme_progression`/`theme`, `tension`, `motifs: [ID, ...]`, and optional
`motif_transformation` to make those features inspectable. Missing annotations
produce null values, not invented prose.

`vertical_matrix.entries` is sparse typed `H_ij(t)`, where
`t=max(source.order, target.order)`. Entries preserve relation, confidence,
strength, endpoints and evidence. Equal endpoint presentation orders are aligned;
all other entries are additionally exposed as `diagonal_dependencies`, retaining
presentation and diegetic gaps. Missing cells mean unencoded relationships, not
agreement, opposition or neutrality.

| Edge | Vertical interpretation |
| --- | --- |
| PARALLELS | harmony |
| CONTRASTS | dissonance |
| CONTRADICTS | contradiction |
| CAUSES / ENABLES | complementarity |
| REQUIRES | dependency |
| MOTIVATES | motivational influence |
| TRANSFORMS | transformation |
| REVEALS | information transfer |
| FORESHADOWS | delayed resonance |
| PAYS_OFF | declared resolution |
| SYMBOLIZES | symbolic reinforcement |

These operational categories describe graph declarations. Dissonance and
contradiction are never automatically penalized. PAYS_OFF does not prove an
ideological contradiction is actually resolved.

`convergence_graph` contains inter-thread edge routes and shared node membership.
A shared scene is convergence, not ideological agreement. `motif_recurrence`
combines explicit motif annotations and SYMBOLIZES relationships to Motif nodes;
appearances at the same node merge their evidence references. `harmony_timeline`
counts typed relations with evidence rather than assigning an unqualified
similarity number. Voice-independence diagnostics expose exclusive nodes,
internal causal relations and distinct declared motivations. Identical thread
memberships are flagged for inspection; no independence score is fabricated.

These are deterministic annotations and graph algorithms. Whether multiple
voices create irreducible meaning remains an interpretive research question
requiring close reading and independent human/model evaluation.
