"""Public rubric definitions. A rubric is not evidence of calibration."""


DIMENSIONS = {
    "B1": {"name": "Story Attention", "definition": "Meaningful dependency and influence, including continuity, setup/payoff connectivity and information flow.", "observable_signals": ["typed declared relationships", "isolated nodes", "setup/payoff connectivity", "attention concentration"], "judgment_question": "Do these relationships support an intelligible and purposeful story?"},
    "B2": {"name": "Setting Utilization", "definition": "Contribution of rules, places and objects to causal, character, thematic or presentation outcomes, without mechanically rewarding reuse.", "observable_signals": ["setting nodes with meaningful incident relations", "unused declared setting elements", "maximum setting degree"], "judgment_question": "Does use of setting feel meaningful without making the world artificially engineered?"},
    "B3": {"name": "Setting Hierarchy", "definition": "Explicit explanatory relationships from world principles and derived rules through institutions and events.", "observable_signals": ["typed rule dependencies", "cycles in declared rule dependencies", "derived rules without declared support"], "judgment_question": "Are the hierarchy and its exceptions coherent and understandable?"},
    "B4": {"name": "Emotional Value", "definition": "Potential attachment, anticipation, empathy, loss, transformation and relief; suffering alone is not emotional depth.", "observable_signals": ["annotated emotional targets", "motivating relationships", "character transformations"], "judgment_question": "Do setup, agency and consequence earn the intended emotion for actual readers?"},
    "B5": {"name": "Information Masking", "definition": "Separated author, character and audience information, with plausible withholding and fair revelation timing.", "observable_signals": ["character knowledge prerequisites", "audience revelation ledger", "declared revelations", "long-range foreshadowing"], "judgment_question": "Are mystery, dramatic irony and silence fair and plausible on a first reading?"},
    "B6": {"name": "Setting Knowledge / Coupling", "definition": "Explanatory coupling among rules, events, objects, people and themes, including unsupported or fragile dependencies.", "observable_signals": ["setting-related edge density", "relations with source evidence", "high-dependency setting nodes"], "judgment_question": "Do connections explain events without unsupported connections or excessive coupling?"},
    "B7": {"name": "Impact / Tension", "definition": "Meaningful stakes, consequences, reversibility, escalation, surprise and turning points; intensity is not impact.", "observable_signals": ["irreversible effects", "declared stakes", "annotated tension progression", "consequence-bearing transitions"], "judgment_question": "Do consequential choices create earned dramatic tension?"},
    "B8": {"name": "Strangeness / Novelty", "definition": "Conceptual originality and creative recombination relative to a specified reference corpus, without rewarding mere bizarreness.", "observable_signals": ["declared novelty claims", "reference corpus identifier", "comparison evidence"], "judgment_question": "What differs meaningfully from comparable works in the stated corpus?"},
    "B9": {"name": "Visual Utilization", "definition": "Screen/game: meaning conveyed through design, environment, composition, movement and editing. Text: expressive sensory imagery and visualizability.", "observable_signals": ["medium-specific visual/sensory intent", "visual motif relationships", "presentation annotations"], "judgment_question": "Does the chosen medium express meaning beyond redundant exposition?"},
}


def rubric(metric_id):
    dimension = DIMENSIONS[metric_id]
    return {
        "scale": "ordinal 0–4; human or explicitly configured evaluator only",
        "question": dimension["judgment_question"],
        "anchors": {"0": "Specific evidence shows the intended function is absent or undermined", "1": "Limited supporting evidence, with major unresolved counterexamples", "2": "Mixed evidence and material tradeoffs", "3": "Consistent supporting evidence, with acknowledged limitations", "4": "Strong, diverse support that survives explicit counterexamples"},
        "calibration_status": "UNCALIBRATED",
        "warning": "These anchors guide review; they do not validate a universal artistic scale. Raw counts never assign a score.",
    }
