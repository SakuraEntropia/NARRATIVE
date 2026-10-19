"""Strict JSON data contracts. Narrative annotations never execute as instructions."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class NodeType(StrEnum):
    STORY = "Story"
    THEME = "Theme"
    ACT = "Act"
    ARC = "Arc"
    SEQUENCE = "Sequence"
    BEAT = "Beat"
    SCENE = "Scene"
    EVENT = "Event"
    CHARACTER = "Character"
    CHARACTER_STATE = "CharacterState"
    WORLD_STATE = "WorldState"
    RULE = "Rule"
    FACT = "Fact"
    HYPOTHESIS = "Hypothesis"
    LOCATION = "Location"
    FACTION = "Faction"
    OBJECT = "Object"
    MOTIF = "Motif"
    FORESHADOWING = "Foreshadowing"
    PAYOFF = "Payoff"
    CONFLICT = "Conflict"
    DECISION = "Decision"
    REVELATION = "Revelation"
    KNOWLEDGE_STATE = "KnowledgeState"


class EdgeType(StrEnum):
    CAUSES = "CAUSES"
    REQUIRES = "REQUIRES"
    ENABLES = "ENABLES"
    CONTRADICTS = "CONTRADICTS"
    FORESHADOWS = "FORESHADOWS"
    PAYS_OFF = "PAYS_OFF"
    SYMBOLIZES = "SYMBOLIZES"
    PARALLELS = "PARALLELS"
    CONTRASTS = "CONTRASTS"
    REVEALS = "REVEALS"
    MOTIVATES = "MOTIVATES"
    TRANSFORMS = "TRANSFORMS"
    BELONGS_TO = "BELONGS_TO"
    PRECEDES = "PRECEDES"
    CONSTRAINS = "CONSTRAINS"
    KNOWS = "KNOWS"
    BELIEVES = "BELIEVES"
    OBSERVES = "OBSERVES"


class CanonStatus(StrEnum):
    CANON = "CANON"
    PROPOSED = "PROPOSED"
    HYPOTHETICAL = "HYPOTHETICAL"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    UNKNOWN = "UNKNOWN"


class Evidence(Record):
    source: str
    excerpt: str = ""
    node_id: str | None = None


class Provenance(Record):
    author: str = "human"
    method: str = "authored"
    model: str | None = None
    operation: str | None = None


class Constraint(Record):
    id: str = Field(min_length=1)
    key: str
    expected: JsonValue
    scope: Literal["invariant", "design"] = "invariant"
    description: str = ""


class State(Record):
    values: dict[str, JsonValue] = Field(default_factory=dict)
    knowledge: dict[str, list[str]] = Field(default_factory=dict)
    beliefs: dict[str, list[str]] = Field(default_factory=dict)
    irreversible: list[str] = Field(default_factory=list)


class Transition(Record):
    requires: dict[str, JsonValue] = Field(default_factory=dict)
    effects: dict[str, JsonValue] = Field(default_factory=dict)
    requires_knowledge: dict[str, list[str]] = Field(default_factory=dict)
    knowledge_updates: dict[str, list[str]] = Field(default_factory=dict)
    belief_updates: dict[str, list[str]] = Field(default_factory=dict)
    irreversible: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class Node(Record):
    id: str = Field(min_length=1)
    kind: NodeType
    label: str
    level: int = Field(default=0, ge=0, le=9)
    parent_id: str | None = None
    status: CanonStatus = CanonStatus.CANON
    locked: bool = False
    time: float = 0
    order: float = 0
    revelation_order: float = 0
    threads: list[str] = Field(default_factory=list)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    transition: Transition | None = None
    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_constraints: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    confidence: float = Field(default=1, ge=0, le=1)
    version: int = Field(default=1, ge=1)
    purpose: str = ""
    duration: float = Field(default=0, ge=0)
    completion: str = "draft"


class Edge(Record):
    id: str = Field(min_length=1)
    source: str
    target: str
    kind: EdgeType
    weight: float = Field(default=1, ge=0, allow_inf_nan=False)
    confidence: float = Field(default=1, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    status: CanonStatus = CanonStatus.CANON
    timestamp: float | None = None
    version: int = Field(default=1, ge=1)


class Project(Record):
    title: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    initial_state: State = Field(default_factory=State)
    constraints: list[Constraint] = Field(default_factory=list)
    medium: Literal["screen", "text", "game"] = "screen"
    version: str = "working"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_ids(self):
        for name in ("nodes", "edges"):
            identifiers = [record.id for record in getattr(self, name)]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate {name} identifiers")
        return self


class Finding(Record):
    code: str
    message: str
    node_ids: list[str] = Field(default_factory=list)
    severity: Literal["error", "warning", "info"] = "error"
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1, ge=0, le=1)
    method: str = "deterministic"
