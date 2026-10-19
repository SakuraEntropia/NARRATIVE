"""Original, explicitly authored fixtures for reproducible offline experiments.

The fixtures are structural test data, not generated prose or evidence of artistic
quality. No existing fictional world is used as a reference corpus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def story_document(variant: str = "original") -> dict[str, Any]:
    """Return an independent JSON-compatible ``The Last Tide Ledger`` project.

    ``weak_motivation`` removes the evidence supporting Mara's final choice.
    ``complex_low_agency`` adds ornamental rules and removes decisive agency.
    """
    if variant not in {"original", "weak_motivation", "complex_low_agency"}:
        raise ValueError(f"Unknown fixture variant: {variant}")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def node(id: str, kind: str, label: str, **kwargs: Any) -> None:
        defaults = {
            "id": id, "kind": kind, "label": label, "status": "CANON",
            "evidence": [{"source": f"fixture:{id}", "node_id": id}], "confidence": 1.0,
            "provenance": {"author": "AI-assisted synthetic fixture", "method": "explicit_authored_fixture"},
        }
        defaults.update(kwargs)
        nodes.append(defaults)

    def edge(source: str, target: str, kind: str, **kwargs: Any) -> None:
        edges.append({
            "id": f"e_{len(edges):03d}", "source": source, "target": target,
            "kind": kind, "weight": 1.0, "confidence": 1.0,
            "evidence": [{"source": f"fixture:{source}", "node_id": source}, {"source": f"fixture:{target}", "node_id": target}],
            "provenance": {"author": "AI-assisted synthetic fixture", "method": "explicit_authored_fixture"},
            **kwargs,
        })

    node("STORY", "Story", "The Last Tide Ledger", level=0,
         purpose="Truth, safety, and civic continuity collide during a tidal evacuation.",
         hard_constraints=[{"id": "preserve_district", "key": "preserve_district", "expected": True, "scope": "design", "description": "The outline must retain the commitment to district survival"}],
         attributes={"preserve_district": True, "premise": "An archivist must expose a falsified flood model while a gate engineer and a councillor pursue incompatible duties."})
    node("THEME", "Theme", "Truth can preserve people while destroying institutions", level=0,
         attributes={"theme": "truth versus stewardship", "intentional_dissonance": True})
    node("ACT_1", "Act", "Evidence before the surge", level=1, parent_id="STORY",
         hard_constraints=[{"id": "preserve_district", "key": "preserve_district", "expected": True, "scope": "design", "description": "The outline must retain the commitment to district survival"}],
         attributes={"preserve_district": True}, purpose="Establish three distinct duties and the one-use mechanism.")
    node("ACT_2", "Act", "Competing obligations", level=1, parent_id="STORY")
    node("ACT_3", "Act", "A public and irreversible choice", level=1, parent_id="STORY")
    node("MARA", "Character", "Mara, tidal records archivist", threads=["mara"],
         attributes={"motivation": "Keep witness testimony publicly usable", "value_conflict": "truth versus anonymity"})
    node("IVO", "Character", "Ivo, floodgate engineer", threads=["ivo"],
         attributes={"motivation": "Evacuate the lower district regardless of official permission", "value_conflict": "public duty versus procedure"})
    node("SERA", "Character", "Sera, continuity councillor", threads=["sera"],
         attributes={"motivation": "Prevent panic and preserve civic trust", "value_conflict": "stewardship versus concealment"})
    node("FUSE_RULE", "Rule", "The manual gate severs its only fuse", time=0, order=1,
         attributes={"world_level": "fundamental", "sensory_detail": "A ceramic fuse becomes black glass after one firing."},
         transition={"effects": {"world.manual_gate_allowed": True}, "consequences": ["Only a manual firing can close the gate during a power loss."]})
    node("SECRET", "Fact", "The council's safe-water model was falsified", locked=True,
         attributes={"secret": True, "author_knows": True, "audience_knows": False})
    node("FUSE_IMAGE", "Foreshadowing", "Ivo displays a spent black fuse", time=1, order=2,
         parent_id="ACT_1", level=2, threads=["ivo"],
         attributes={"visual_intent": "The unbroken white fuse is framed beside the spent black one.", "motifs": ["BLACK_GLASS"], "theme": "one-use responsibility"})
    node("BLACK_GLASS", "Motif", "Black glass records an action that cannot be undone")
    node("PROMISE", "Scene", "Mara promises displaced witnesses a public record", time=2, order=3,
         parent_id="ACT_1", level=2, threads=["mara"],
         attributes={"motivation": "The witnesses' protection depends on public acknowledgement", "emotion": "attachment", "theme": "truth", "stakes": "Witnesses will disappear from relief rolls without a record", "tension": 2},
         transition={"participants": ["MARA"], "effects": {"character.mara.committed_to_witnesses": True}, "knowledge_updates": {"MARA": ["witnesses_need_public_record"]}})
    node("DELAY", "Decision", "Sera postpones publication to finish evacuation", time=3, order=4,
         parent_id="ACT_1", level=2, threads=["sera"],
         attributes={"motivation": "A panic at the causeway would prevent evacuation", "emotion": "dread", "theme": "stewardship", "value_conflict": "safety versus accountability", "stakes": "The last causeway is overcrowded", "tension": 3},
         transition={"participants": ["SERA"], "effects": {"world.publication_delayed": True}})
    node("CRACKS", "Scene", "Ivo measures cracks beneath the tide gauge", time=4, order=5,
         parent_id="ACT_1", level=2, threads=["ivo"],
         attributes={"motivation": "Test the physical gate instead of trusting the council model", "emotion": "alarm", "theme": "care through work", "tension": 4, "sensory_detail": "Saltwater pulses through a chalk line."},
         transition={"participants": ["IVO"], "effects": {"world.gate_risk_verified": True}, "knowledge_updates": {"IVO": ["gate_at_risk"]}})
    # Interleaved scenes retain independent thread changes instead of duplicating
    # the protagonist's information. They deliberately separate setup and payoff.
    for index in range(1, 13):
        thread = ("mara", "ivo", "sera")[(index - 1) % 3]
        character = thread.upper()
        labels = {
            "mara": f"Mara verifies witness register {index}",
            "ivo": f"Ivo moves evacuation chain {index}",
            "sera": f"Sera negotiates shelter allocation {index}",
        }
        purposes = {
            "mara": "Preserve named evidence before the archive floods",
            "ivo": "Make the gate reachable without waiting for council orders",
            "sera": "Keep rival districts cooperating during evacuation",
        }
        node(f"INTERLUDE_{index:02d}", "Scene", labels[thread], time=4 + index,
             order=5 + index, parent_id="ACT_2", level=2, threads=[thread],
             purpose=purposes[thread], duration=1,
             attributes={"motivation": purposes[thread], "emotion": ("resolve", "strain", "restraint")[(index - 1) % 3],
                         "theme": ("truth", "care through work", "stewardship")[(index - 1) % 3],
                         "tension": 3 + index / 4},
             transition={"participants": [character], "effects": {f"character.{thread}.progress_{index}": True}})
        if index > 3:
            edge(f"INTERLUDE_{index - 3:02d}", f"INTERLUDE_{index:02d}", "ENABLES")
    node("TESTIMONY", "Hypothesis", "A dockworker claims the archive can survive underwater",
         time=17, order=18, status="HYPOTHETICAL", threads=["mara"],
         attributes={"unreliable_testimony": True}, transition={"effects": {"world.archive_waterproof": True}})
    node("REVEAL", "Revelation", "Mara compares the original gauge with the signed model", time=18, order=19,
         parent_id="ACT_2", level=2, threads=["mara", "sera"],
         attributes={"motivation": "Resolve the mismatch before evacuation deadlines", "audience_knows": ["SECRET"], "theme": "truth", "emotion": "betrayal", "tension": 8},
         transition={"participants": ["MARA"], "requires": {"world.model_falsified": True},
                     "effects": {"world.testimony_verified": True}, "knowledge_updates": {"MARA": ["SECRET"], "audience": ["SECRET"]}})
    node("PREPARE_GATE", "Event", "Ivo links the public beacon to the manual gate", time=19, order=20,
         parent_id="ACT_3", level=2, threads=["ivo"],
         hard_constraints=[{"id": "gate_available", "key": "world.manual_gate_allowed", "expected": True, "scope": "invariant", "description": "Preparation requires the established manual mechanism"}],
         attributes={"motivation": "Let a public witness trigger rescue even if the council refuses", "emotion": "resolve", "theme": "public duty", "tension": 8},
         transition={"participants": ["IVO"], "requires": {"world.manual_gate_allowed": True, "world.gate_risk_verified": True},
                     "effects": {"world.gate_ready": True}, "resources": ["resource.fuse.intact"]})
    node("SERA_CONCEDES", "Decision", "Sera signs the correction and risks her office", time=20, order=21,
         parent_id="ACT_3", level=2, threads=["sera"],
         attributes={"motivation": "A correction signed in public can preserve trust better than concealment", "emotion": "shame", "theme": "stewardship", "value_conflict": "institutional survival versus responsibility", "tension": 9},
         transition={"participants": ["SERA"], "requires_knowledge": {"SERA": ["SECRET"]},
                     "effects": {"world.correction_signed": True, "character.sera.in_office": False}, "irreversible": ["character.sera.in_office"]})
    node("CLIMAX", "Decision", "Mara broadcasts the ledger and fires the gate", time=21, order=22,
         parent_id="ACT_3", level=2, threads=["mara", "ivo", "sera"],
         attributes={"motivation": "Keep her promise to the witnesses even though publication exposes her identity", "emotion": "fear and resolve", "stakes": "The district floods if she waits; she loses anonymity if she acts", "theme": "truth versus stewardship", "value_conflict": "collective safety versus private safety", "tension": 10, "climax": True,
                     "repair_candidates": [
                         {"id": "restore_witness_commitment", "kind": "motivation", "node_id": "CLIMAX", "changes": {"attributes.motivation": "Keep the promise recorded at PROMISE: witnesses need a public record despite the cost of exposure"}, "evidence": ["PROMISE", "REVEAL"], "cost": 1.0, "provenance": {"author": "AI-assisted synthetic fixture", "method": "explicit_authored_candidate"}},
                         {"id": "recall_witness_risk", "kind": "motivation", "node_id": "CLIMAX", "changes": {"attributes.motivation": "Publication prevents the named witnesses from being excluded from relief; Mara accepts loss of anonymity"}, "evidence": ["PROMISE", "SECRET"], "cost": 1.5, "provenance": {"author": "AI-assisted synthetic fixture", "method": "explicit_authored_candidate"}},
                     ]},
         transition={"participants": ["MARA"], "requires": {"world.manual_gate_allowed": True, "world.gate_ready": True, "world.testimony_verified": True, "world.correction_signed": True, "resource.fuse.intact": True},
                     "requires_knowledge": {"MARA": ["SECRET", "witnesses_need_public_record"]},
                     "effects": {"world.district_safe": True, "world.archive_accessible": False, "character.mara.anonymous": False, "resource.fuse.intact": False},
                     "knowledge_updates": {"public": ["SECRET"]}, "irreversible": ["character.mara.anonymous", "resource.fuse.intact"],
                     "consequences": ["Mara can no longer hide her identity", "The original archive is sealed beneath the gate"]})
    node("PAYOFF", "Payoff", "The fuse turns black as the dry causeway fills with witnesses", time=22, order=23,
         parent_id="ACT_3", level=2, threads=["ivo", "mara"],
         attributes={"visual_intent": "The same white fuse from the opening shot is now black; witnesses read the broadcast ledger.", "motifs": ["BLACK_GLASS"], "emotion": "relief and loss", "theme": "a public record outlasts its archive", "tension": 2},
         transition={"requires": {"world.district_safe": True, "resource.fuse.intact": False}, "participants": ["IVO", "MARA"]})
    node("AFTERMATH", "Scene", "Sera joins the relief queue under her own name", time=23, order=24,
         parent_id="ACT_3", level=2, threads=["sera"],
         attributes={"motivation": "Accept the same public accountability as the residents", "emotion": "humility", "theme": "stewardship without office", "tension": 1},
         transition={"requires": {"character.sera.in_office": False}, "participants": ["SERA"]})
    for source, target, kind in [
        ("FUSE_RULE", "PREPARE_GATE", "REQUIRES"), ("FUSE_RULE", "CLIMAX", "CONSTRAINS"),
        ("FUSE_IMAGE", "PAYOFF", "FORESHADOWS"), ("PAYOFF", "FUSE_IMAGE", "PAYS_OFF"),
        ("FUSE_IMAGE", "BLACK_GLASS", "SYMBOLIZES"), ("PAYOFF", "BLACK_GLASS", "SYMBOLIZES"),
        ("PROMISE", "CLIMAX", "MOTIVATES"), ("SECRET", "REVEAL", "REQUIRES"),
        ("REVEAL", "CLIMAX", "ENABLES"), ("CRACKS", "PREPARE_GATE", "CAUSES"),
        ("PREPARE_GATE", "CLIMAX", "ENABLES"), ("SERA_CONCEDES", "CLIMAX", "ENABLES"),
        ("CLIMAX", "PAYOFF", "CAUSES"), ("SERA_CONCEDES", "AFTERMATH", "CAUSES"),
        ("DELAY", "SERA_CONCEDES", "TRANSFORMS"), ("PROMISE", "DELAY", "CONTRASTS"),
        ("DELAY", "REVEAL", "CONTRADICTS"), ("THEME", "CLIMAX", "SYMBOLIZES"),
        ("INTERLUDE_10", "REVEAL", "ENABLES"), ("INTERLUDE_11", "PREPARE_GATE", "ENABLES"),
        ("INTERLUDE_12", "SERA_CONCEDES", "MOTIVATES"),
    ]:
        edge(source, target, kind)
    if variant == "weak_motivation":
        climax = next(n for n in nodes if n["id"] == "CLIMAX")
        climax["attributes"].pop("motivation")
        edges[:] = [e for e in edges if not (e["target"] == "CLIMAX" and e["kind"] == "MOTIVATES")]
        climax["attributes"]["intentional_defect"] = "A climactic decision has lost its stated motive and incoming motivation evidence."
    if variant == "complex_low_agency":
        for n in nodes:
            if n["kind"] == "Decision":
                n["attributes"].pop("motivation", None)
                n["attributes"]["agency_override"] = "external mechanism determines outcome"
                if n.get("transition"):
                    n["transition"]["participants"] = []
        edges[:] = [e for e in edges if e["kind"] != "MOTIVATES"]
        for index in range(24):
            node(f"ORNAMENT_{index:02d}", "Rule", f"Unused tidal registry convention {index}",
                 attributes={"world_level": "derived", "ornamental": True,
                             "exposition": "A descriptive registry convention with no consequences in the represented events."})
    return {
        "title": "The Last Tide Ledger", "medium": "screen", "version": variant,
        "nodes": nodes, "edges": edges,
        "initial_state": {
            "values": {"world.model_falsified": True, "resource.fuse.intact": True,
                       "character.mara.anonymous": True, "character.sera.in_office": True,
                       "world.archive_accessible": True, "world.district_safe": False},
            "knowledge": {"author": ["SECRET"], "SERA": ["SECRET"], "MARA": [], "IVO": [], "audience": []},
            "beliefs": {"MARA": ["archive_should_survive"]},
        },
        "constraints": [],
        "metadata": {"synthetic": True, "authorship": "Original deterministic fixture authored for NARRATIVE",
                     "variant": variant, "limitations": "Annotations exercise structural mechanisms; they are not calibrated artistic judgments.",
                     "critical_long_range_dependency": ["FUSE_IMAGE", "PAYOFF"]},
    }


def example_graph(variant: str = "original"):
    """Load a fresh typed graph; importing this module has no filesystem effects."""
    from narrative.core.graph import StoryGraph
    from narrative.core.schema import Project

    return StoryGraph(Project.model_validate(story_document(variant)))


def write_examples(directory: str | Path) -> list[Path]:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for variant in ("original", "weak_motivation", "complex_low_agency"):
        path = destination / f"{variant}.json"
        path.write_text(json.dumps(story_document(variant), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        files.append(path)
    return files
