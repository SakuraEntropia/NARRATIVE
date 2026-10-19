# Benchmark and adversarial evaluation protocol

`narrative.evaluation.benchmarks.evaluate(graph)` computes offline observations
for B1–B9. Every record exposes metric ID, name, definition, observable signals,
operational observations, scoring rubric, evidence, counterevidence, confidence,
model score, optional human score, effective score, story version and method.

All model scores and artistic confidence values are **null by default**. The
implementation does not call a model or simulate reader reactions. Counts and
graph occupancy never turn into invented art grades. Null means unmeasured,
not zero. The supplied rubric has no external calibration.

## Nine dimensions

| ID | Observations actually computed | Unmeasured judgment |
| --- | --- | --- |
| B1 Story Attention | Concentration, dependency density, isolated components, setup/payoff connectivity | Meaningfulness, intentional continuity and influence |
| B2 Setting Utilization | Setting element count, elements with meaningful relations, unused elements, maximum degree | Effective contribution without artificial overuse |
| B3 Setting Hierarchy | Typed Rule dependencies, strongly connected dependency components, explicitly derived Rules without incoming support | Explanatory adequacy and justified exceptions |
| B4 Emotional Value | Emotional annotations, MOTIVATES and TRANSFORMS edges | Actual attachment, empathy and earned emotional response |
| B5 Information Masking | Simulated knowledge failures, author facts, REVEALS edges, separated audience ledger | Fair withholding, dramatic irony and comprehensibility |
| B6 Setting Knowledge/Coupling | Setting-related edges, supplied source evidence, unsupported links, maximum degree | Explanatory value, fragility and excessive coupling |
| B7 Impact/Tension | Irreversible events, annotated stakes, consequence transitions, tension trajectory | Felt stakes, surprise and meaningful dramatic impact |
| B8 Strangeness/Novelty | Explicit novelty claims and declared reference corpus | Comparative originality; no corpus search is performed |
| B9 Visual Utilization | Medium, visual or sensory annotations, visual motif relations | Expressive success beyond repeated exposition |

Setting elements are Rules, WorldStates, Objects, Locations and Factions. Their
use requires an incident causal, constraint, motivating, transformative,
symbolic, parallel, contrast, setup/payoff or revelation relationship. This is
an operational proxy; atmosphere may contribute without any encoded edge.
Rule hierarchy uses only Rule-to-Rule REQUIRES, CONSTRAINS and CAUSES edges.
Cycles prompt inspection and do not by themselves prove inconsistency.

For `screen` and `game`, B9 uses visual annotations. For `text`, it additionally
uses `sensory_detail`. The system cannot determine whether dialogue redundantly
explains an image without actual scene/prose interpretation.

Results retain separate `measurement_groups.structural`, `.proxy` and
`.subjective` dictionaries. Structural means reproducible for the encoded
graph; proxy means a declared annotation or count with a hypothesized artistic
relationship; subjective means an unevaluated reader-experience question.
Declared medium/corpus metadata is labelled separately in observations.

## Rubric and human calibration

The optional ordinal rubric uses anchors 0–4: absent/undermined function;
limited support with major counterexamples; mixed evidence; consistent support
with limitations; strong evidence surviving counterexamples. An actual evaluator
must cite evidence and counterevidence. These are review aids, not validated
interval-scale measurements of quality.

`apply_human_ratings(report, ratings)` creates a new report. Each rating requires
`metric_id`, numeric `score` from 0 through 4, `evaluator`, and `rationale`.
An optional `version` must match the story version. Stale ratings and invalid
scores raise errors. Human ratings override the effective value while preserving
the model estimate and rating history. The same records can be supplied through
`Project.metadata.human_ratings`.

```python
from narrative.evaluation.calibration import apply_human_ratings

rated = apply_human_ratings(report, [{
    "metric_id": "B4", "score": 3, "evaluator": "reader-01",
    "rationale": "The earlier sacrifice supported the climactic attachment",
    "evidence": ["SCENE_2", "CLIMAX"], "version": report["version"],
}])
```

Human annotation changes the status to `HUMAN_ANNOTATED_UNCALIBRATED`; one rating
does not validate a scale. Population calibration, inter-rater reliability,
cross-model agreement, held-out reader studies and corpus-based novelty
evaluation remain unimplemented research work.

## Preferences and sensitivity

The quality vector contains individual effective scores, usually null.
There is no default aggregate and no automatic art winner.

`aggregate(scores, weights)` requires explicit nonnegative weights and actual
scores for every positively weighted objective. Missing values raise instead of
being silently assigned zero or renormalized away. Aggregating ordinal labels
is an optional preference calculation with known limitations.

`weight_sensitivity(vectors, weights, relative_change=.25)` exposes the baseline
ranking and each one-at-a-time ±25% weight perturbation. Rankings, aggregates,
changed weights and ranking changes remain inspectable. This is local preference
sensitivity, not measurement uncertainty. `pareto_front(vectors)` retains all
nondominated candidates, including tradeoffs and ties, and rejects incomplete or
mismatched objective sets. These helpers operate on the rubric's rated values;
they do not impute structural counts as artistic scores.

## Safeguards

Eleven evidence-bearing safeguards remain visible independently of artistic
preferences:

- Causal consistency uses actual graph validation and state-machine failures.
- Agency counts Decisions with participants and consequences/effects.
- Motivation reports Decisions without a declared motivation or incoming
  MOTIVATES edge; missing annotation is not proof of irrationality.
- Thematic coherence exposes relations, retaining deliberate contradictions.
- Structural closure reports unresolved obligations and intended open endings.
- Economy exposes unused setting components and duplicate typed relations.
- Accessibility exposes knowledge problems and missing purpose annotations.
- Pacing exposes declared durations and tension annotations. Summed hierarchy
  durations may overlap and are not claimed as a real runtime.
- Information burden exposes introduced fact IDs and prerequisite counts,
  without claiming to measure cognitive load.
- Artistic risk preserves explicit project risk annotations, without a grade.
- Narrative debt preserves explicit obligations and unconnected setups.

Hard failures block structural eligibility even if a human prefers another
dimension. Increasing density, node count, suffering, lore, symmetry or thread
count never mechanically improves a score. Original evidence and counterexamples
must remain available after a revision.

## Adversarial protocol

`narrative.evaluation.adversarial.review(graph)` applies eight named role
checklists: architect, structural critic, character critic, audience critic,
artistic critic, red-team critic, defender and judge. They are deterministic
inspection roles, not independent autonomous model agents.

The audit explicitly covers twelve failure modes: fake foreshadowing;
coincidental resolution; contrived twists; exposition disguised as revelation;
arbitrary rule changes; personality reversal; symbolic links replacing claimed
causality; excessive symmetry; unresolved mystery; complexity mistaken for
depth; emotion without setup; and theories contradicted by executed events.

Checks distinguish actual simulator failures from annotation gaps and
counterexample questions. For example, symbolism without a causal path is not
invalid symbolism: it prompts inspection only if someone claims it explains
events. Explicit `rule_revision` and `personality_reversal` annotations permit
support checks. An explicitly annotated `exposition_tokens >= 600` prompts a
scene review; that threshold is not a calibrated artistic verdict. Checks with
no evidence return `not_established`, never a synthetic pass.

First-time and expert perspectives remain separate. First-time inspection
exposes knowledge and motivation gaps. Expert inspection exposes long-range
setups, world rules and cross-thread relations. Their coexistence can trigger a
**potential** discrepancy report. It is not an observed response from either
reader group, and the perspectives are never averaged into one score.

The defender can explain possible intentional devices but must point to
supporting evidence. It cannot overrule failed invariants with rhetoric. The
judge returns structural eligibility and unresolved review count; its artistic
winner is null without external judgments. `compare_candidates({name: graph})`
retains per-candidate reports, eligible branches and pairwise review questions.
No elaborate defense or negative criticism wins by itself.

All reports state zero model calls and retain story version. Independent model
configuration and actual population reader studies must be added before claiming
cross-evaluator agreement, validated artistic improvements or reader preference.
