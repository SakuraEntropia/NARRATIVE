"""Evidence-grounded deterministic adversarial audit and explicit review gaps.

Role names identify checklists, not autonomous LLMs. No reader response is
fabricated. Counterexamples are questions to test unless a rule check fails.
"""

import networkx as nx

from narrative.analysis.attention import canonical, token
from narrative.analysis.polyphony import analyze_polyphony

from .benchmarks import evaluate


def _check(name, node_ids, evidence, challenge, limitation):
    return {"failure_mode": name, "status": "review_needed" if node_ids or evidence else "not_established", "node_ids": sorted(set(node_ids)), "evidence": sorted(set(evidence)), "counterexample_to_test": challenge, "confidence": None, "method": "deterministic_structural_proxy", "limitation": limitation}


def review(graph, benchmark=None):
    report = benchmark if benchmark is not None else evaluate(graph)
    nodes, edges = canonical(graph)
    incoming = {key: [edge for edge in edges if edge.target == key] for key in nodes}
    causal = nx.DiGraph()
    causal.add_nodes_from(nodes)
    causal.add_edges_from((edge.source, edge.target) for edge in edges if token(edge.kind) in {"CAUSES", "ENABLES", "MOTIVATES"})
    foreshadowing = [edge for edge in edges if token(edge.kind) == "FORESHADOWS"]
    unsupported_setup = [edge for edge in foreshadowing if not edge.evidence or nodes[edge.source].order >= nodes[edge.target].order]
    uncaused_payoffs = [node.id for node in nodes.values() if token(node.kind) == "PAYOFF" and not any(token(edge.kind) in {"CAUSES", "ENABLES", "REQUIRES", "MOTIVATES"} for edge in incoming[node.id])]
    unsupported_revelations = [node.id for node in nodes.values() if token(node.kind) == "REVELATION" and not any(token(edge.kind) in {"CAUSES", "ENABLES", "REQUIRES", "FORESHADOWS", "OBSERVES"} for edge in incoming[node.id])]
    exposition = [node.id for node in nodes.values() if isinstance(node.attributes.get("exposition_tokens"), (int, float)) and node.attributes["exposition_tokens"] >= 600]
    rule_changes = [node.id for node in nodes.values() if node.attributes.get("rule_revision") and not any(token(edge.kind) in {"CAUSES", "REQUIRES", "CONSTRAINS"} for edge in incoming[node.id])]
    reversals = [node.id for node in nodes.values() if node.attributes.get("personality_reversal") and not any(token(edge.kind) in {"TRANSFORMS", "MOTIVATES", "CAUSES"} for edge in incoming[node.id])]
    symbolic_only = [edge for edge in edges if token(edge.kind) == "SYMBOLIZES" and not nx.has_path(causal, edge.source, edge.target) and not nx.has_path(causal, edge.target, edge.source)]
    polyphony = analyze_polyphony(graph)
    symmetry = polyphony["diagnostics"]["structural_redundancy"]
    debt = report["safeguards"]["unresolved_narrative_debt"]["observations"]
    unsupported_choices = report["safeguards"]["character_motivation_consistency"]["observations"]["decisions_without_declared_motivation"]
    emotional_unsupported = [key for key in unsupported_choices if nodes[key].attributes.get("emotion") or nodes[key].attributes.get("emotional_target")]
    errors = report["safeguards"]["causal_consistency"]["observations"]["errors"]
    contradictions = [edge for edge in edges if token(edge.kind) == "CONTRADICTS"]
    checks = [
        _check("fake_foreshadowing", [edge.source for edge in unsupported_setup], [edge.id for edge in unsupported_setup], "Could a first-time reader infer a relevant possibility from the setup before learning the payoff?", "Missing source evidence or nonforward presentation is a review prompt; it does not prove fake foreshadowing."),
        _check("coincidental_causal_resolution", uncaused_payoffs, uncaused_payoffs, "Remove the alleged cause: does the resolution still happen without a changed prerequisite?", "Only missing declared causal support is checked; coincidence can be intentional."),
        _check("contrived_plot_twists", unsupported_revelations, unsupported_revelations, "Can a reader reconstruct a supported chain of clues without newly invented rules?", "Semantic surprise and fairness need reader review."),
        _check("exposition_dump_as_revelation", exposition, exposition, "Does removing this explanation leave the dramatic event unchanged?", "600 explicitly annotated exposition tokens is an inspection threshold, not an artistic verdict."),
        _check("arbitrary_rule_changes", rule_changes, rule_changes, "Is the exception established before the event depends on it?", "Only explicit rule_revision annotations without support are flagged; simulation separately enforces encoded physics."),
        _check("character_personality_reversal", reversals, reversals, "Which earlier pressure or transformation makes this reversal intelligible?", "Only explicit personality_reversal annotations are checked; ordinary motive changes are not automatically contradictions."),
        _check("symbolic_connections_without_causal_support", [edge.source for edge in symbolic_only], [edge.id for edge in symbolic_only], "If a thematic link is claimed as an explanation of events, where is the causal chain?", "Symbolic meaning need not be causal. This check prevents substituting symbolism for a claimed cause, and never invalidates symbolism itself."),
        _check("excessive_narrative_symmetry", [key for item in symmetry for key in item["evidence"]], [key for item in symmetry for key in item["evidence"]], "What independent contribution disappears when one mirrored voice is removed?", "Identical thread membership is only a structural redundancy proxy; intentional mirroring can be valuable."),
        _check("mystery_without_payoff", [item["node_id"] for item in debt["obligations"] if not item["intentional"]], [item["node_id"] for item in debt["obligations"]], "Is the unresolved obligation an intentional open question, and is that intention encoded?", "Payoff connectivity does not establish satisfaction; intentional open endings are allowed."),
        _check("worldbuilding_complexity_as_depth", [], [], "Compare a simpler branch with equal causal coverage and stronger agency; do actual readers prefer the complexity?", "Setting counts and coupling are reported without a depth score; empirical pairwise reader comparison has not run."),
        _check("emotion_without_setup", emotional_unsupported, emotional_unsupported, "Which attachment, motivation or prior choice earns the intended emotional response?", "Missing motivation annotation cannot establish emotional manipulation."),
        _check("elegant_theory_contradicts_events", [key for item in errors for key in item["node_ids"]], [edge.id for edge in contradictions] + [item["code"] for item in errors], "Does the interpretation survive replay of every encoded state transition?", "Executable contradictions are hard evidence only relative to encoded state semantics; thematic contradictions may be deliberate."),
    ]
    by_name = {check["failure_mode"]: check for check in checks}
    first_time = {"perspective": "First-Time / Ordinary Reader", "observations": {"unearned_character_knowledge": report["information_masking"]["unearned_knowledge"], "unsupported_revelations": unsupported_revelations, "motivation_gaps": unsupported_choices, "audience_ledger_annotations": len(report["information_masking"]["audience_timeline"])}, "questions": ["Is each consequential choice comprehensible without consulting lore notes?", "Is required information available before the audience must interpret the choice?"], "reader_score": None, "method": "deterministic_review_prompts; no reader experiment performed"}
    expert = {"perspective": "Expert / Lore-Aware Reader", "observations": {"long_range_setup_edges": [edge.id for edge in foreshadowing if abs(nodes[edge.target].order - nodes[edge.source].order) > 1], "cross_thread_relations": len(polyphony["vertical_matrix"]["entries"]), "world_rule_count": sum(token(node.kind) == "RULE" for node in nodes.values())}, "questions": ["Do long-range references alter the causal or thematic interpretation?", "Would this connection still matter if the explanatory lore were removed?"], "reader_score": None, "method": "deterministic_review_prompts; no expert response measured"}
    discrepancy = bool((unsupported_revelations or unsupported_choices) and (expert["observations"]["long_range_setup_edges"] or expert["observations"]["cross_thread_relations"]))
    roles = {
        "architect": {"proposals": [{"operation": "review_missing_motivation", "node_id": key, "status": "PROPOSED", "evidence": [key]} for key in unsupported_choices], "method": "rule_based_candidate_prompts"},
        "structural_critic": {"findings": errors, "checks": [by_name[name] for name in ("coincidental_causal_resolution", "arbitrary_rule_changes", "mystery_without_payoff")]},
        "character_critic": {"checks": [by_name[name] for name in ("character_personality_reversal", "emotion_without_setup")], "motivation_gaps": unsupported_choices},
        "audience_critic": {"first_time": first_time, "expert": expert},
        "artistic_critic": {"checks": [by_name[name] for name in ("symbolic_connections_without_causal_support", "excessive_narrative_symmetry", "worldbuilding_complexity_as_depth")], "artistic_score": None},
        "red_team_critic": {"checks": checks},
        "defender": {"responses": [{"failure_mode": check["failure_mode"], "status": "requires_evidence", "argument": check["limitation"], "evidence": check["evidence"]} for check in checks if check["status"] == "review_needed"], "rule": "Rhetorical explanations never override failed state invariants; intentional devices still need explicit supporting evidence."},
        "judge": {"structural_gate": "fail" if errors else "pass_for_encoded_constraints", "unresolved_review_count": sum(check["status"] == "review_needed" for check in checks), "winner": None, "reason": "Hard failures block automatic acceptance. Artistic disagreements remain open without independent model or human judgments."},
    }
    return {"method": "deterministic_adversarial_checklists_v1", "version": graph.document.version, "roles": roles, "failure_mode_checks": checks, "perspectives": {"first_time": first_time, "expert": expert, "discrepancy": {"status": "review_needed" if discrepancy else "not_established", "evidence": sorted(set(unsupported_revelations + unsupported_choices)), "interpretation": "Encoded lore connections coexist with first-time comprehension gaps; this is a potential discrepancy, not an observed reader response.", "averaged_score": None}}, "provenance": {"evaluator": "offline_rules", "independent_models": [], "model_calls": 0, "benchmark_version": report["version"]}, "limitations": ["Role checklists do not simulate independent minds or reader emotions.", "All artistic challenges require actual model/human review; null scores are intentional.", "Missing annotation is not proof of a defect, and a passing audit is not proof of artistic quality."]}


def compare_candidates(candidates):
    """Preserve disagreements and hard failures instead of inventing a winner."""
    reports = {name: review(graph) for name, graph in candidates.items()}
    return {"candidates": reports, "structurally_eligible": sorted(name for name, report in reports.items() if report["roles"]["judge"]["structural_gate"] != "fail"), "pairwise_questions": [{"a": a, "b": b, "question": "Which candidate better earns its choices and emotion on a first reading, and what specific evidence supports that preference?"} for index, a in enumerate(sorted(candidates)) for b in sorted(candidates)[index + 1:]], "winner": None, "limitation": "No independent reader/model pairwise preference supplied; structural eligibility is not artistic superiority."}
