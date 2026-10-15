import pytest
from pydantic import ValidationError

from videostudio.schemas import (
    CINEMATIC_SHOT_JSON_SCHEMA,
    SAVE_THE_CAT_15_BEATS,
    STORY_CIRCLE_8_STEPS,
    ActionElement,
    BeatEntry,
    BeatSheet,
    CharacterElement,
    CinematicShotSpecification,
    DialogueElement,
    ParentheticalElement,
    SceneCard,
    SceneHeadingElement,
    ScreenJSONDocument,
    ScreenJSONScene,
    ThematicDossier,
    TransitionElement,
    lint_observable_action,
    validate_shot_against_json_schema,
)


def test_cinematic_shot_specification_validates_against_draft_2020_12_schema():
    payload = {
        "shot_id": "SC01_SH01",
        "scene_context": {
            "location": "LOC_OBSERVATORY_DOME",
            "time_of_day": "NIGHT",
            "environment_state": "Rain streaking across fractured glass dome, cold mist indoors",
        },
        "subject": {
            "character_ref": "CHAR_ELENA_VANCE",
            "action_core": "Elena rotates the brass azimuth ring until the relay locks into place",
            "subtext_expression": "Jaw clenched, eyes darting toward the airlock indicator",
            "wardrobe_id": "WARD_ELENA_EVA_TRENCH",
            "prop_interactions": ["PROP_CHRONO_COMPASS:opened"],
        },
        "cinematography": {
            "framing": "medium_close_up",
            "camera_angle": "low_angle",
            "camera_movement": "dolly_in",
            "lens": "35mm_cinematic",
            "composition": "Rule of thirds, subject framed left against glowing star chart",
        },
        "lighting_and_atmosphere": {
            "setup": "Chiaroscuro",
            "color_palette": "Cold cyan and amber instrument glow",
            "color_grade": "Teal & Orange",
            "volumetrics": "Dense low-lying cryo fog illuminated by console",
        },
        "temporal_dynamics": {
            "duration_seconds": 4.5,
            "frame_rate": 24,
            "motion_intensity": 0.42,
        },
        "consistency_anchors": {
            "reference_image_uris": [
                "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_front.png",
                "canon/bible/locations/LOC_OBSERVATORY_DOME/base_render.png",
            ],
            "preserve_elements": [
                "facial_geometry:CHAR_ELENA_VANCE",
                "scar_left_brow",
                "PROP_CHRONO_COMPASS",
            ],
        },
    }

    assert CINEMATIC_SHOT_JSON_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert CINEMATIC_SHOT_JSON_SCHEMA["title"] == "CinematicShotSpecification"

    validate_shot_against_json_schema(payload)
    shot = CinematicShotSpecification.model_validate(payload)
    assert shot.shot_id == "SC01_SH01"
    assert shot.cinematography.framing == "medium_close_up"
    assert shot.temporal_dynamics.frame_rate == 24


def test_cinematic_shot_rejects_invalid_optical_enums_and_temporal_bounds():
    bad_payload = {
        "shot_id": "SC01_SH02",
        "scene_context": {
            "location": "LOC_OBSERVATORY_DOME",
            "time_of_day": "NIGHT",
            "environment_state": "Clear",
        },
        "subject": {
            "character_ref": "CHAR_ELENA_VANCE",
            "action_core": "Walks forward",
            "subtext_expression": "Alert",
        },
        "cinematography": {
            "framing": "super_duper_wide",  # Invalid enum
            "camera_angle": "eye_level",
            "camera_movement": "static",
            "lens": "50mm_standard",
        },
        "lighting_and_atmosphere": {
            "setup": "Rembrandt",
            "color_palette": "Warm",
            "color_grade": "Kodachrome",
        },
        "temporal_dynamics": {
            "duration_seconds": 25.0,  # Exceeds 15.0 max
            "frame_rate": 25,  # Invalid frame rate (must be 24, 30, or 60)
            "motion_intensity": 1.5,  # Exceeds 1.0 max
        },
        "consistency_anchors": {
            "reference_image_uris": ["canon/ref.png"],
            "preserve_elements": ["identity"],
        },
    }

    with pytest.raises(Exception):
        validate_shot_against_json_schema(bad_payload)

    with pytest.raises(ValidationError):
        CinematicShotSpecification.model_validate(bad_payload)


def test_screenjson_strips_unfilmable_internal_thoughts_and_exports_fountain():
    cleaned = lint_observable_action(
        "Elena wonders if her brother betrayed the fleet as she slams the bulkhead lever down."
    )
    assert "wonders if" not in cleaned.lower()
    assert "slams the bulkhead lever down" in cleaned

    scene = ScreenJSONScene(
        scene_id="SC01",
        initial_state={"bulkhead": "open", "alarm": "silent"},
        terminal_state={"bulkhead": "sealed", "alarm": "klaxon_active"},
        heading=SceneHeadingElement(
            context="INT",
            setting="OBSERVATORY DOME",
            time_of_day="NIGHT",
            lighting_lock="Chiaroscuro",
            color_palette_lock="Teal & Orange",
        ),
        elements=[
            ActionElement(
                description="Elena slams the brass bulkhead lever down. Red klaxons pulse across the wet steel."
            ),
            CharacterElement(
                character_id="CHAR_ELENA_VANCE",
                name="ELENA VANCE",
                base_bible_anchor_key="canon/bible/characters/CHAR_ELENA_VANCE",
            ),
            ParentheticalElement(
                micro_expression="eyes narrowed, breath misting",
                emotional_cadence="clipped urgency",
            ),
            DialogueElement(
                character_id="CHAR_ELENA_VANCE",
                spoken_string="Seal the upper ring before the telemetry array floods.",
                language_identifier="en-US",
            ),
            TransitionElement(transition_type="CUT TO:"),
        ],
    )

    doc = ScreenJSONDocument(
        episode_id="S01E01",
        title="The Azimuth Signal",
        scenes=[scene],
    )
    fountain_text = doc.to_fountain()
    assert "INT. OBSERVATORY DOME - NIGHT" in fountain_text
    assert "ELENA VANCE" in fountain_text
    assert "(eyes narrowed, breath misting; clipped urgency)" in fountain_text
    assert "Seal the upper ring before the telemetry array floods." in fountain_text
    assert "CUT TO:" in fountain_text
    assert all(el.uuid for el in scene.elements)


def test_beat_sheet_enforces_causal_scene_linking_and_pivots():
    beats = [
        BeatEntry(
            beat_index=idx + 1,
            beat_name=name,
            summary=f"Dramatic execution of {name}",
            dramatic_tension=0.3 + (idx * 0.04),
        )
        for idx, name in enumerate(SAVE_THE_CAT_15_BEATS)
    ]
    cards = [
        SceneCard(
            scene_id="SC01",
            beat_name="Opening Image",
            dramatic_objective="Calibrate the deep-space relay",
            active_obstacle="Geomagnetic interference",
            character_stakes="Loss of outpost contact",
            initial_state={"relay_status": "offline"},
            terminal_state={"relay_status": "calibrated"},
            causal_predecessor_scene_id=None,
        ),
        SceneCard(
            scene_id="SC02",
            beat_name="Catalyst",
            dramatic_objective="Decode anomalous signal on calibrated relay",
            active_obstacle="Encrypted carrier wave",
            character_stakes="Discovery of lost expedition",
            initial_state={"relay_status": "calibrated"},
            terminal_state={"relay_status": "calibrated", "signal_decoded": "true"},
            causal_predecessor_scene_id="SC01",
        ),
    ]

    sheet = BeatSheet(
        episode_id="S01E01",
        framework="save_the_cat_15",
        beats=beats,
        scene_cards=cards,
        pacing_score=0.92,
        dramatic_curve_valid=True,
    )
    assert sheet.validate_causal_chain() is True
    assert len(STORY_CIRCLE_8_STEPS) == 8
