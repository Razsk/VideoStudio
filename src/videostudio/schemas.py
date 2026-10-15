from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Literal, Optional, Union

import jsonschema
from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Controlled Vocabularies & Canonical Structural Constants
# ---------------------------------------------------------------------------

SAVE_THE_CAT_15_BEATS: List[str] = [
    "Opening Image",
    "Theme Stated",
    "Set-Up",
    "Catalyst",
    "Debate",
    "Break into Two",
    "B Story",
    "Fun and Games",
    "Midpoint",
    "Bad Guys Close In",
    "All Is Lost",
    "Dark Night of the Soul",
    "Break into Three",
    "Finale",
    "Final Image",
]

STORY_CIRCLE_8_STEPS: List[str] = [
    "1. You (A character is in a zone of comfort)",
    "2. Need (But they want something)",
    "3. Go (They enter an unfamiliar situation)",
    "4. Search (Adapt to it)",
    "5. Find (Get what they wanted)",
    "6. Take (Pay a heavy price for it)",
    "7. Return (Then return to their familiar situation)",
    "8. Change (Having changed)",
]

FramingScale = Literal[
    "extreme_wide",
    "wide",
    "medium_full",
    "medium",
    "medium_close_up",
    "close_up",
    "extreme_close_up",
]

CameraAngle = Literal[
    "eye_level",
    "low_angle",
    "high_angle",
    "dutch_angle",
    "birds_eye",
    "worms_eye",
]

CameraMovement = Literal[
    "static",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "dolly_in",
    "dolly_out",
    "tracking",
    "crane",
    "arc",
]

LensFocalLength = Literal[
    "18mm_ultra_wide",
    "24mm_wide",
    "35mm_cinematic",
    "50mm_standard",
    "85mm_portrait",
    "135mm_telephoto",
    "anamorphic",
]

LightingParadigm = Literal[
    "Rembrandt",
    "Chiaroscuro",
    "High-Key",
    "Low-Key Silhouette",
    "Volumetric Split",
    "Practicals",
]

ColorGradingPreset = Literal[
    "Bleach Bypass",
    "Technicolor 3-Strip",
    "Teal & Orange",
    "Monochromatic Desaturated",
    "Kodachrome",
]

# Exact JSON Schema (Draft 2020-12) from the Architectural Blueprint
CINEMATIC_SHOT_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CinematicShotSpecification",
    "type": "object",
    "required": [
        "shot_id",
        "scene_context",
        "subject",
        "cinematography",
        "lighting_and_atmosphere",
        "temporal_dynamics",
        "consistency_anchors",
    ],
    "properties": {
        "shot_id": {"type": "string"},
        "scene_context": {
            "type": "object",
            "required": ["location", "time_of_day", "environment_state"],
            "properties": {
                "location": {"type": "string"},
                "time_of_day": {"type": "string"},
                "environment_state": {"type": "string"},
            },
        },
        "subject": {
            "type": "object",
            "required": ["character_ref", "action_core", "subtext_expression"],
            "properties": {
                "character_ref": {"type": "string"},
                "action_core": {"type": "string"},
                "subtext_expression": {"type": "string"},
                "wardrobe_id": {"type": "string"},
                "prop_interactions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "cinematography": {
            "type": "object",
            "required": ["framing", "camera_angle", "camera_movement", "lens"],
            "properties": {
                "framing": {
                    "type": "string",
                    "enum": [
                        "extreme_wide",
                        "wide",
                        "medium_full",
                        "medium",
                        "medium_close_up",
                        "close_up",
                        "extreme_close_up",
                    ],
                },
                "camera_angle": {
                    "type": "string",
                    "enum": [
                        "eye_level",
                        "low_angle",
                        "high_angle",
                        "dutch_angle",
                        "birds_eye",
                        "worms_eye",
                    ],
                },
                "camera_movement": {
                    "type": "string",
                    "enum": [
                        "static",
                        "pan_left",
                        "pan_right",
                        "tilt_up",
                        "tilt_down",
                        "dolly_in",
                        "dolly_out",
                        "tracking",
                        "crane",
                        "arc",
                    ],
                },
                "lens": {
                    "type": "string",
                    "enum": [
                        "18mm_ultra_wide",
                        "24mm_wide",
                        "35mm_cinematic",
                        "50mm_standard",
                        "85mm_portrait",
                        "135mm_telephoto",
                        "anamorphic",
                    ],
                },
                "composition": {"type": "string"},
            },
        },
        "lighting_and_atmosphere": {
            "type": "object",
            "required": ["setup", "color_palette", "color_grade"],
            "properties": {
                "setup": {"type": "string"},
                "color_palette": {"type": "string"},
                "color_grade": {"type": "string"},
                "volumetrics": {"type": "string"},
            },
        },
        "temporal_dynamics": {
            "type": "object",
            "required": ["duration_seconds", "frame_rate", "motion_intensity"],
            "properties": {
                "duration_seconds": {"type": "number", "minimum": 1.0, "maximum": 15.0},
                "frame_rate": {"type": "integer", "enum": [24, 30, 60]},
                "motion_intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        "consistency_anchors": {
            "type": "object",
            "required": ["reference_image_uris", "preserve_elements"],
            "properties": {
                "reference_image_uris": {"type": "array", "items": {"type": "string"}},
                "preserve_elements": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


def validate_shot_against_json_schema(payload: Dict[str, Any]) -> None:
    """Validate a raw dictionary against the Draft 2020-12 CinematicShotSpecification schema."""
    validator = jsonschema.Draft202012Validator(CINEMATIC_SHOT_JSON_SCHEMA)
    validator.validate(payload)


# ---------------------------------------------------------------------------
# Phase I: Thematic Dossier & Phase II: Beat Sheet / Scene Cards
# ---------------------------------------------------------------------------


class ThematicDossier(BaseModel):
    """Output data contract of the Research and Lore Agent."""

    episode_id: str
    story_seed: str
    premise: str
    tone: str
    target_conflicts: List[str]
    immutable_facts: List[str]
    lore_entities_referenced: List[str] = Field(default_factory=list)
    tonal_precedents: List[str] = Field(default_factory=list)
    setting_adherence_score: float = Field(ge=0.0, le=1.0)


class BeatEntry(BaseModel):
    beat_index: int
    beat_name: str
    summary: str
    dramatic_tension: float = Field(ge=0.0, le=1.0)


class SceneCard(BaseModel):
    """Self-contained scene unit decomposed from a structural beat with causal state linking."""

    scene_id: str
    beat_name: str
    dramatic_objective: str
    active_obstacle: str
    character_stakes: str
    initial_state: Dict[str, str] = Field(default_factory=dict)
    terminal_state: Dict[str, str] = Field(default_factory=dict)
    causal_predecessor_scene_id: Optional[str] = None


class BeatSheet(BaseModel):
    """Output data contract of the Director Agent."""

    episode_id: str
    framework: Literal["save_the_cat_15", "story_circle_8"] = "save_the_cat_15"
    beats: List[BeatEntry]
    scene_cards: List[SceneCard]
    pacing_score: float = Field(ge=0.0, le=1.0)
    dramatic_curve_valid: bool = True

    def validate_causal_chain(self) -> bool:
        """
        Verify that the terminal state of Scene N directly informs the initial conditions
        of Scene N+1 whenever a causal predecessor is declared.
        """
        card_map = {card.scene_id: card for card in self.scene_cards}
        for card in self.scene_cards:
            if card.causal_predecessor_scene_id:
                pred = card_map.get(card.causal_predecessor_scene_id)
                if pred is None:
                    raise ValueError(
                        f"Scene {card.scene_id} references unknown predecessor {card.causal_predecessor_scene_id}"
                    )
                for key, val in card.initial_state.items():
                    if key in pred.terminal_state and pred.terminal_state[key] != val:
                        raise ValueError(
                            f"Causal state mismatch between {pred.scene_id} terminal_state[{key}]="
                            f"{pred.terminal_state[key]} and {card.scene_id} initial_state[{key}]={val}"
                        )
        return True


# ---------------------------------------------------------------------------
# Phase II: ScreenJSON Serialization Standard & Fountain Exporter
# ---------------------------------------------------------------------------

_UNFILMABLE_PATTERNS = [
    re.compile(
        r"\b(?:wonders if|remembers how|thinks about|reflects on|realizes inside|ponders whether|hopes that|fears that)[^.,;]*?\b(?=(?:as|while|when)\s+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:he|she|they|[A-Z][a-z]+)\s+(?:wonders if|remembers how|thinks about|reflects on|realizes inside|ponders whether|hopes that|fears that)[^.,;]*?[.,;]\s*",
        re.IGNORECASE,
    ),
]


def lint_observable_action(text: str) -> str:
    """
    Restrict action lines to strictly observable visual and auditory events,
    stripping un-filmable internal thoughts to prepare text directly for diffusion models.
    """
    cleaned = text.strip()
    # Strip patterns like "Elena wonders if ... as she slams..." -> "Elena slams..."
    clause_match = re.sub(
        r"^([A-Z][a-zA-Z0-9_\- ]*?)\s+(?:wonders if|remembers how|thinks about|reflects on|ponders whether|internally feels)[^.,;]*?\s+(?:as|while|when)\s+(?:he|she|they)\s+",
        r"\1 ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = clause_match
    for pat in _UNFILMABLE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


class SceneHeadingElement(BaseModel):
    element_type: Literal["scene_heading"] = "scene_heading"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: Literal["INT", "EXT", "INT/EXT"]
    setting: str
    time_of_day: str
    lighting_lock: str = "Chiaroscuro"
    color_palette_lock: str = "Teal & Orange"

    def to_fountain(self) -> str:
        return f"{self.context}. {self.setting.upper()} - {self.time_of_day.upper()}"


class ActionElement(BaseModel):
    element_type: Literal["action"] = "action"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str

    @field_validator("description")
    @classmethod
    def enforce_observable_action(cls, v: str) -> str:
        return lint_observable_action(v)


class CharacterElement(BaseModel):
    element_type: Literal["character"] = "character"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str
    name: str
    base_bible_anchor_key: str


class ParentheticalElement(BaseModel):
    element_type: Literal["parenthetical"] = "parenthetical"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    micro_expression: str
    emotional_cadence: str


class DialogueElement(BaseModel):
    element_type: Literal["dialogue"] = "dialogue"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str
    spoken_string: str
    language_identifier: str = "en-US"


class TransitionElement(BaseModel):
    element_type: Literal["transition"] = "transition"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transition_type: str = "CUT TO:"


ScreenJSONElement = Union[
    SceneHeadingElement,
    ActionElement,
    CharacterElement,
    ParentheticalElement,
    DialogueElement,
    TransitionElement,
]


class ScreenJSONScene(BaseModel):
    scene_id: str
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    beat_name: str = "Opening Image"
    heading: SceneHeadingElement
    elements: List[ScreenJSONElement] = Field(default_factory=list)
    initial_state: Dict[str, str] = Field(default_factory=dict)
    terminal_state: Dict[str, str] = Field(default_factory=dict)

    def to_fountain(self) -> str:
        lines: List[str] = [self.heading.to_fountain(), ""]
        for el in self.elements:
            if isinstance(el, ActionElement):
                lines.append(el.description)
                lines.append("")
            elif isinstance(el, CharacterElement):
                lines.append(el.name.upper())
            elif isinstance(el, ParentheticalElement):
                lines.append(f"({el.micro_expression}; {el.emotional_cadence})")
            elif isinstance(el, DialogueElement):
                lines.append(el.spoken_string)
                lines.append("")
            elif isinstance(el, TransitionElement):
                t_str = el.transition_type if el.transition_type.endswith(":") else f"{el.transition_type}:"
                lines.append(f"> {t_str}")
                lines.append("")
        return "\n".join(lines).strip()


class ScreenJSONDocument(BaseModel):
    """Standardized ScreenJSON AST Screenplay."""

    episode_id: str
    title: str
    author: str = "VideoStudio Multi-Agent Pipeline"
    scenes: List[ScreenJSONScene]
    dialogue_naturalism_score: float = Field(default=0.94, ge=0.0, le=1.0)
    subtext_faithfulness_score: float = Field(default=0.91, ge=0.0, le=1.0)

    def to_fountain(self) -> str:
        header = [
            f"Title: {self.title}",
            "Credit: Written by",
            f"Author: {self.author}",
            f"Draft date: Episode {self.episode_id}",
            "",
            "====",
            "",
        ]
        scene_blocks = [scene.to_fountain() for scene in self.scenes]
        return "\n".join(header) + "\n\n".join(scene_blocks) + "\n"


# ---------------------------------------------------------------------------
# Phase III: CinematicShotSpecification Models
# ---------------------------------------------------------------------------


class SceneContextSpec(BaseModel):
    location: str
    time_of_day: str
    environment_state: str


class SubjectSpec(BaseModel):
    character_ref: str
    action_core: str
    subtext_expression: str
    wardrobe_id: Optional[str] = None
    prop_interactions: List[str] = Field(default_factory=list)


class CinematographySpec(BaseModel):
    framing: FramingScale
    camera_angle: CameraAngle
    camera_movement: CameraMovement
    lens: LensFocalLength
    composition: Optional[str] = None


class LightingAndAtmosphereSpec(BaseModel):
    setup: str
    color_palette: str
    color_grade: str
    volumetrics: Optional[str] = None


class TemporalDynamicsSpec(BaseModel):
    duration_seconds: float = Field(ge=1.0, le=15.0)
    frame_rate: Literal[24, 30, 60] = 24
    motion_intensity: float = Field(ge=0.0, le=1.0)


class ConsistencyAnchorsSpec(BaseModel):
    reference_image_uris: List[str]
    preserve_elements: List[str]


class CinematicShotSpecification(BaseModel):
    """Validated JSON Shot Prompt Specification for generative video engines."""

    shot_id: str
    scene_context: SceneContextSpec
    subject: SubjectSpec
    cinematography: CinematographySpec
    lighting_and_atmosphere: LightingAndAtmosphereSpec
    temporal_dynamics: TemporalDynamicsSpec
    consistency_anchors: ConsistencyAnchorsSpec
    prompt_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    beat_name: str = "Opening Image"
    dialogue_line: Optional[str] = None
    dialogue_language: str = "en-US"
    negative_constraints: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_draft_2020_12_compliance(self) -> "CinematicShotSpecification":
        core_dict = {
            "shot_id": self.shot_id,
            "scene_context": self.scene_context.model_dump(exclude_none=True),
            "subject": self.subject.model_dump(exclude_none=True),
            "cinematography": self.cinematography.model_dump(exclude_none=True),
            "lighting_and_atmosphere": self.lighting_and_atmosphere.model_dump(exclude_none=True),
            "temporal_dynamics": self.temporal_dynamics.model_dump(exclude_none=True),
            "consistency_anchors": self.consistency_anchors.model_dump(exclude_none=True),
        }
        validate_shot_against_json_schema(core_dict)
        return self
