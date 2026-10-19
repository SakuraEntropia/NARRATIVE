"""Nine benchmark dimensions with observations, uncertainty and no invented art grades."""

from collections import Counter

import networkx as nx

from narrative.analysis.attention import NARRATIVE_KINDS, _references, analyze_attention, canonical, token
from narrative.analysis.information_masking import analyze_information
from narrative.analysis.narrative_debt import analyze_debt
from narrative.analysis.polyphony import analyze_polyphony

from .calibration import apply_human_ratings
from .rubrics import DIMENSIONS, rubric


SETTING_KINDS = {"RULE", "WORLDSTATE", "OBJECT", "LOCATION", "FACTION"}
MEANINGFUL = {"CAUSES", "REQUIRES", "ENABLES", "CONSTRAINS", "MOTIVATES", "TRANSFORMS", "SYMBOLIZES", "PARALLELS", "CONTRASTS", "FORESHADOWS", "PAYS_OFF", "REVEALS"}


def _signal(value, method, evidence=()):
    return {"value": value, "method": method, "evidence": list(evidence)}


def _safeguard(observations, evidence, limitation, flagged=False):
    return {"observations": observations, "evidence": evidence, "status": "review" if flagged else "observed", "artistic_score": None, "limitation": limitation}


def evaluate(graph):
    """Compute actual structural/proxy observations; leave subjective scores null.

    Optional metadata.human_ratings is processed with explicit provenance. No
    model provider is invoked by this offline deterministic evaluation.
    """
    nodes, edges = canonical(graph)
    document = graph.document
    attention = analyze_attention(graph)
    debt = analyze_debt(graph)
    polyphony = analyze_polyphony(graph)
    structural_findings = graph.validate()
    # State-machine execution, rather than the explanatory graph, determines
    # whether prerequisites, irreversibility and knowledge actually hold.
    from narrative.core.state_machine import simulate
    simulation = simulate(graph)
    information = analyze_information(graph, simulation)
    findings = [finding.model_dump(mode="json") for finding in [*structural_findings, *simulation.findings]]
    unique_findings = {str((item["code"], item["message"], item["node_ids"])): item for item in findings}
    findings = list(unique_findings.values())
    setting = {key for key, node in nodes.items() if token(node.kind) in SETTING_KINDS}
    setting_edges = [edge for edge in edges if (edge.source in setting or edge.target in setting) and token(edge.kind) in MEANINGFUL]
    used_setting = {endpoint for edge in setting_edges for endpoint in (edge.source, edge.target) if endpoint in setting}
    unused_setting = sorted(setting - used_setting)
    degree = Counter(endpoint for edge in setting_edges for endpoint in (edge.source, edge.target) if endpoint in setting)
    rules = {key for key, node in nodes.items() if token(node.kind) == "RULE"}
    rule_edges = [edge for edge in edges if edge.source in rules and edge.target in rules and token(edge.kind) in {"REQUIRES", "CONSTRAINS", "CAUSES"}]
    rule_graph = nx.DiGraph()
    rule_graph.add_nodes_from(rules)
    rule_graph.add_edges_from((edge.source, edge.target) for edge in rule_edges)
    cycles = sorted((sorted(group) for group in nx.strongly_connected_components(rule_graph) if len(group) > 1 or any(rule_graph.has_edge(key, key) for key in group)), key=lambda group: group[0])
    unsupported_derived = sorted(key for key in rules if nodes[key].attributes.get("derived") and not any(edge.target == key for edge in rule_edges))
    emotional = [node for node in nodes.values() if node.attributes.get("emotion") or node.attributes.get("emotional_target")]
    motivation_edges = [edge for edge in edges if token(edge.kind) == "MOTIVATES"]
    transformations = [edge for edge in edges if token(edge.kind) == "TRANSFORMS"]
    decisions = [node for node in nodes.values() if token(node.kind) == "DECISION"]
    unsupported_choices = sorted(node.id for node in decisions if not node.attributes.get("motivation") and not any(edge.target == node.id for edge in motivation_edges))
    transitions = [node for node in nodes.values() if node.transition]
    irreversible = [node for node in transitions if node.transition.irreversible]
    consequence = [node for node in transitions if node.transition.effects or node.transition.consequences]
    agentic = [node for node in decisions if node.transition and node.transition.participants and (node.transition.effects or node.transition.consequences)]
    stakes = [node for node in nodes.values() if node.attributes.get("stakes")]
    tensions = [{"node_id": node.id, "order": node.order, "tension": node.attributes["tension"], "evidence": _references(node)} for node in sorted(nodes.values(), key=lambda node: (node.order, node.id)) if "tension" in node.attributes]
    screened = document.medium in {"screen", "game"}
    visual = [node for node in nodes.values() if node.attributes.get("visual_intent") or node.attributes.get("visual") or (not screened and node.attributes.get("sensory_detail"))]
    narrative_nodes = [node for node in nodes.values() if token(node.kind) in NARRATIVE_KINDS]
    declarations = [node for node in nodes.values() if node.attributes.get("novelty_claim")]
    supplied_evidence = [edge for edge in setting_edges if edge.evidence]
    stats = {
        "B1": ({"attention_concentration": _signal(attention["metrics"]["attention_concentration"]["value"], "structural"), "dependency_density": _signal(attention["metrics"]["narrative_dependency_density"]["value"], "structural", [edge.id for edge in edges]), "orphaned_nodes": _signal(attention["metrics"]["orphaned_narrative_nodes"]["node_ids"], "structural"), "setup_payoff": _signal(attention["metrics"]["setup_to_payoff_connectivity"], "structural")}, [edge.id for edge in edges], attention["metrics"]["orphaned_narrative_nodes"]["node_ids"]),
        "B2": ({"setting_elements": _signal(len(setting), "structural", sorted(setting)), "utilized_elements": _signal(len(used_setting), "proxy", sorted(used_setting)), "unused_elements": _signal(unused_setting, "proxy", unused_setting), "maximum_setting_degree": _signal(max(degree.values(), default=0), "structural")}, [edge.id for edge in setting_edges], unused_setting),
        "B3": ({"rule_dependencies": _signal(len(rule_edges), "structural", [edge.id for edge in rule_edges]), "dependency_cycles": _signal(cycles, "structural"), "unsupported_derived_rules": _signal(unsupported_derived, "proxy", unsupported_derived)}, [edge.id for edge in rule_edges], unsupported_derived + [key for group in cycles for key in group]),
        "B4": ({"emotional_targets": _signal(len(emotional), "proxy", [node.id for node in emotional]), "motivating_edges": _signal(len(motivation_edges), "proxy", [edge.id for edge in motivation_edges]), "transformations": _signal(len(transformations), "proxy", [edge.id for edge in transformations]), "reader_effectiveness": _signal(None, "subjective")}, [node.id for node in emotional] + [edge.id for edge in transformations], unsupported_choices),
        "B5": ({"unearned_knowledge": _signal(information["unearned_knowledge"], "structural"), "author_fact_count": _signal(len(information["author_facts"]), "structural", information["author_facts"]), "revelation_edges": _signal(sum(token(edge.kind) == "REVEALS" for edge in edges), "structural", [edge.id for edge in edges if token(edge.kind) == "REVEALS"]), "withholding_fairness": _signal(None, "subjective")}, [edge.id for edge in edges if token(edge.kind) in {"REVEALS", "FORESHADOWS", "KNOWS"}], [item["node_id"] for item in information["unearned_knowledge"]]),
        "B6": ({"setting_related_edges": _signal(len(setting_edges), "structural", [edge.id for edge in setting_edges]), "source_supported_relations": _signal(len(supplied_evidence), "proxy", [edge.id for edge in supplied_evidence]), "relations_without_source_evidence": _signal([edge.id for edge in setting_edges if not edge.evidence], "proxy"), "maximum_coupling": _signal(max(degree.values(), default=0), "structural")}, [edge.id for edge in setting_edges], [edge.id for edge in setting_edges if not edge.evidence]),
        "B7": ({"irreversible_events": _signal(len(irreversible), "structural", [node.id for node in irreversible]), "declared_stakes": _signal(len(stakes), "proxy", [node.id for node in stakes]), "consequence_bearing_transitions": _signal(len(consequence), "structural", [node.id for node in consequence]), "tension_trajectory": _signal(tensions, "proxy"), "experienced_impact": _signal(None, "subjective")}, [node.id for node in irreversible + stakes], unsupported_choices),
        "B8": ({"novelty_claims": _signal(len(declarations), "proxy", [node.id for node in declarations]), "reference_corpus": _signal(document.metadata.get("reference_corpus"), "declared_metadata"), "comparative_originality": _signal(None, "subjective")}, [node.id for node in declarations], ["No corpus-based originality assessment was performed"]),
        "B9": ({"medium": _signal(document.medium, "declared_metadata"), "annotated_expression_nodes": _signal(len(visual), "proxy", [node.id for node in visual]), "visual_relationships": _signal(len(attention["sparse_matrices"]["visual"]), "proxy", [entry["edge_id"] for entry in attention["sparse_matrices"]["visual"]]), "expressive_success": _signal(None, "subjective")}, [node.id for node in visual], [] if visual else ["No medium-specific expression annotations"]),
    }
    dimensions = {}
    groups = {"structural": {}, "proxy": {}, "subjective": {}}
    for metric_id, (observations, evidence, counterevidence) in stats.items():
        definition = DIMENSIONS[metric_id]
        for name, signal in observations.items():
            if signal["method"] in groups:
                groups[signal["method"]][f"{metric_id}.{name}"] = signal
        dimensions[metric_id] = {"metric_id": metric_id, "name": definition["name"], "definition": definition["definition"], "observable_signals": definition["observable_signals"], "observations": observations, "scoring_rubric": rubric(metric_id), "evidence": sorted(set(evidence)), "counterevidence": counterevidence, "confidence": None, "confidence_note": "Observation formulas are deterministic; confidence in artistic interpretation is uncalibrated and therefore unspecified.", "model_score": None, "human_score": None, "effective_score": None, "effective_score_source": None, "version": document.version, "evaluation_method": "deterministic_structural_and_annotation_proxies; no model evaluation", "limitations": ["Absence of an annotation is not proof of an artistic defect.", "Source references preserve traceability but are not independently verified.", "Counts do not automatically become quality scores."]}
    errors = [item for item in findings if item["severity"] == "error"]
    thematic_edges = [edge for edge in edges if token(edge.kind) in {"PARALLELS", "CONTRASTS", "CONTRADICTS", "SYMBOLIZES"}]
    durations = [node.duration for node in narrative_nodes]
    burdens = [{"node_id": node.id, "introduced_facts": len({fact for facts in node.transition.knowledge_updates.values() for fact in facts}) if node.transition else 0, "incoming_dependencies": sum(edge.target == node.id and token(edge.kind) in {"REQUIRES", "CONSTRAINS"} for edge in edges)} for node in narrative_nodes]
    safeguards = {
        "causal_consistency": _safeguard({"errors": errors, "applied_transitions": simulation.applied}, sorted({key for item in errors for key in item["node_ids"]}), "Graph/state validity checks encoded facts; it cannot establish the plausibility of unstated causes.", bool(errors)),
        "character_agency": _safeguard({"decisions": len(decisions), "participant_and_consequence_decisions": len(agentic)}, [node.id for node in agentic], "A transition proxy cannot establish the felt freedom or meaningfulness of a choice.", bool(decisions and not agentic)),
        "character_motivation_consistency": _safeguard({"decisions_without_declared_motivation": unsupported_choices}, unsupported_choices, "Missing annotation is an audit prompt; semantic consistency of motives needs review.", bool(unsupported_choices)),
        "thematic_coherence": _safeguard({"thematic_relations": len(thematic_edges), "polyphony_relations": len(polyphony["vertical_matrix"]["entries"])}, [edge.id for edge in thematic_edges], "Contradictions and dissonance are retained without an automatic penalty."),
        "structural_closure": _safeguard(debt, [item["node_id"] for item in debt["obligations"]], "Open endings can be intentional; connection does not guarantee satisfying closure.", bool(debt["unintentional_count"])),
        "narrative_economy": _safeguard({"unused_setting_elements": unused_setting, "redundant_relations": attention["metrics"]["redundant_attention"]["groups"]}, unused_setting, "Atmosphere, rhythm and intentional repetition can justify apparent unused material."),
        "accessibility": _safeguard({"unearned_knowledge": information["unearned_knowledge"], "unannotated_purpose_nodes": [node.id for node in narrative_nodes if not node.purpose]}, [item["node_id"] for item in information["unearned_knowledge"]], "Reader comprehensibility is unmeasured; test first-time readers separately."),
        "pacing": _safeguard({"declared_total_duration": sum(durations), "duration_range": [min(durations), max(durations)] if durations else None, "tension_trajectory": tensions}, [node.id for node in narrative_nodes], "Durations can overlap across hierarchy levels; sum is descriptive and not runtime or pacing quality."),
        "information_burden": _safeguard({"per_node": burdens}, [item["node_id"] for item in burdens], "Dependency count and introduced ledgers do not measure cognitive load."),
        "artistic_risk": _safeguard({"declared_risks": document.metadata.get("artistic_risks", [])}, [], "No deterministic novelty or artistic-risk grade is justified."),
        "unresolved_narrative_debt": _safeguard(debt, [item["node_id"] for item in debt["obligations"]], debt["limitation"], bool(debt["unintentional_count"])),
    }
    report = {"method": "offline_evidence_bearing_diagnostics_v1", "version": document.version, "dimensions": dimensions, "measurement_groups": groups, "quality_vector": {key: None for key in DIMENSIONS}, "weighted_aggregate": None, "safeguards": safeguards, "calibration": {"status": "UNCALIBRATED", "human_overrides_model": True, "human_rating_history": [], "model_evaluator": None, "warning": "No external reader calibration or model judgments supplied; no universal artistic score is claimed."}, "anti_goodhart": ["Hard structural violations remain visible independently of artistic preferences.", "More nodes, reuse, density, suffering, symmetry or threads never automatically increase a score.", "Counterevidence and unsupported declarations remain visible.", "Use independent reader judgments, pairwise preference and weight sensitivity before choosing a branch."], "information_masking": information, "limitations": ["B4, B8 and experiential portions of other dimensions require actual reader/model evaluation.", "No LLM or corpus comparison ran; model_score is null in all nine dimensions.", "This benchmark is an unvalidated research instrument, not proof of story quality."]}
    ratings = document.metadata.get("human_ratings", [])
    return apply_human_ratings(report, ratings) if ratings else report
