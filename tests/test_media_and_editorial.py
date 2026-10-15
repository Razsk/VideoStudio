from pathlib import Path

import opentimelineio as otio
import pytest

from videostudio.continuity import ContinuityLedger, SpatialScreenDirection
from videostudio.editorial import (
    construct_editorial_timeline,
    export_timeline_otio,
    timeline_to_summary_dict,
)
from videostudio.lore import seed_default_canon
from videostudio.media import (
    KeyframeCandidate,
    SharedAttentionKeyframeSynthesizer,
    VLMContinuityJudge,
    apply_revision_delta_to_shot,
    synthesize_dialogue_wav,
    synthesize_i2v_motion_clip,
)
from videostudio.schemas import CinematicShotSpecification
from videostudio.storage import StudioStorage


def _sample_shot(shot_id: str = "SC01_SH01") -> CinematicShotSpecification:
    return CinematicShotSpecification.model_validate(
        {
            "shot_id": shot_id,
            "scene_context": {
                "location": "LOC_OBSERVATORY_DOME",
                "time_of_day": "NIGHT",
                "environment_state": "Sub-polar sleet against dome glass",
            },
            "subject": {
                "character_ref": "CHAR_ELENA_VANCE",
                "action_core": "Elena locks the brass azimuth vernier into position",
                "subtext_expression": "Focused intensity, jaw set",
                "wardrobe_id": "WARD_ELENA_EVA_TRENCH",
                "prop_interactions": ["ART_CHRONO_COMPASS:opened"],
            },
            "cinematography": {
                "framing": "medium_close_up",
                "camera_angle": "low_angle",
                "camera_movement": "dolly_in",
                "lens": "35mm_cinematic",
                "composition": "Rule of thirds, left-weighted",
            },
            "lighting_and_atmosphere": {
                "setup": "Chiaroscuro",
                "color_palette": "Cold cyan and amber instrument glow",
                "color_grade": "Teal & Orange",
                "volumetrics": "Low cryo mist",
            },
            "temporal_dynamics": {
                "duration_seconds": 3.5,
                "frame_rate": 24,
                "motion_intensity": 0.45,
            },
            "consistency_anchors": {
                "reference_image_uris": [
                    "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_front.png"
                ],
                "preserve_elements": [
                    "facial_geometry:CHAR_ELENA_VANCE",
                    "ART_CHRONO_COMPASS",
                ],
            },
            "beat_name": "Catalyst",
            "dialogue_line": "Beacon Nine is still transmitting from inside the shadow.",
        }
    )


def test_keyframe_first_policy_and_semantic_loop_recovery(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    seed_default_canon(storage)
    elena = storage.load_character_bible("CHAR_ELENA_VANCE")

    ledger = ContinuityLedger(episode_id="S01E01")
    entry = ledger.append_shot_state(
        scene_shot_id="SC01_SH01",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={"CHAR_ELENA_VANCE": ["rain_drenched"]},
        prop_registry_affordance={"ART_CHRONO_COMPASS": "opened"},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_DOME",
            camera_side="north_of_axis",
            subject_facing="left_to_right",
            eyeline_vector="east",
        ),
        lighting_environmental={"time_of_day": "NIGHT", "lighting_setup": "Chiaroscuro"},
        causal_reveal_flags=["BEACON_9_ACTIVE"],
    )

    shot = _sample_shot("SC01_SH01")
    synthesizer = SharedAttentionKeyframeSynthesizer(storage=storage, season=1, episode=1)
    judge = VLMContinuityJudge(id_score_threshold=0.85)

    # Simulate an initial candidate keyframe suffering identity drift (score < 0.85)
    drifted_candidates = synthesizer.synthesize_scene_grid(
        scene_id="SC01",
        shots=[shot],
        character_bibles={"CHAR_ELENA_VANCE": elena},
        ledger_entries={"SC01_SH01": entry},
        simulate_drift_for_shots={"SC01_SH01"},
    )
    cand = drifted_candidates[0]
    assert (tmp_path / cand.image_path).exists()
    assert (tmp_path / cand.grid_contact_sheet_path).exists()

    verdict = judge.evaluate(cand, shot, elena, entry)
    assert verdict.accepted is False
    assert verdict.identity_score < 0.85
    assert verdict.revision_delta is not None

    # Disallow I2V motion diffusion on unverified keyframe!
    with pytest.raises(PermissionError, match="Keyframe-first policy violation"):
        synthesize_i2v_motion_clip(
            storage=storage,
            season=1,
            episode=1,
            shot=shot,
            keyframe=cand,
            ledger_entry=entry,
        )

    # Apply Semantic Loop RevisionDelta and re-synthesize
    refined_shot = apply_revision_delta_to_shot(shot, verdict.revision_delta)
    refined_candidates = synthesizer.synthesize_scene_grid(
        scene_id="SC01",
        shots=[refined_shot],
        character_bibles={"CHAR_ELENA_VANCE": elena},
        ledger_entries={"SC01_SH01": entry},
    )
    verified_cand = refined_candidates[0]
    verdict2 = judge.evaluate(verified_cand, refined_shot, elena, entry)
    assert verdict2.accepted is True
    assert verdict2.identity_score >= 0.85
    verified_cand.verified = True
    verified_cand.identity_score = verdict2.identity_score

    # Now I2V motion diffusion succeeds and passes frame-stepping inspection
    clip_result = synthesize_i2v_motion_clip(
        storage=storage,
        season=1,
        episode=1,
        shot=refined_shot,
        keyframe=verified_cand,
        ledger_entry=entry,
    )
    assert (tmp_path / clip_result.video_path).exists()
    assert clip_result.frame_stepping_passed is True

    wav_path = synthesize_dialogue_wav(
        storage=storage,
        season=1,
        episode=1,
        shot=refined_shot,
    )
    assert wav_path.exists()


def test_construct_editorial_timeline_otio_lineage_and_markers(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    shot_manifest = [
        {
            "shot_id": "SC01_SH01",
            "duration_sec": 3.5,
            "video_path": "season_01/episode_01/media/SC01_SH01_master.mp4",
            "audio_path": "season_01/episode_01/media/SC01_SH01_dialogue.wav",
            "prompt_uuid": "uuid-prompt-001",
            "model_version": "veo-3-i2v-1.2",
            "seed": 42001,
            "ledger_idx": 0,
            "beat_name": "Opening Image",
        },
        {
            "shot_id": "SC01_SH02",
            "duration_sec": 4.0,
            "video_path": "season_01/episode_01/media/SC01_SH02_master.mp4",
            "audio_path": "season_01/episode_01/media/SC01_SH02_dialogue.wav",
            "prompt_uuid": "uuid-prompt-002",
            "model_version": "veo-3-i2v-1.2",
            "seed": 42002,
            "ledger_idx": 1,
            "beat_name": "Catalyst",
        },
    ]

    timeline = construct_editorial_timeline("S01E01", shot_manifest)
    assert timeline.name == "Episode_S01E01_Assembly"
    assert len(timeline.tracks) >= 2
    v_track = timeline.tracks[0]
    a_track = timeline.tracks[1]
    assert v_track.name == "V1_Master_Video"
    assert a_track.name == "A1_Dialogue"
    assert len(v_track) == 2

    first_clip = v_track[0]
    assert first_clip.name == "SC01_SH01"
    assert first_clip.metadata["generative_lineage"]["prompt_uuid"] == "uuid-prompt-001"
    assert first_clip.metadata["generative_lineage"]["seed"] == 42001
    assert first_clip.metadata["generative_lineage"]["continuity_ledger_index"] == 0
    assert len(first_clip.markers) == 1
    assert first_clip.markers[0].name == "Beat: Opening Image"
    assert first_clip.markers[0].color == otio.schema.MarkerColor.CYAN

    otio_path = export_timeline_otio(timeline, storage, season=1, episode=1)
    assert otio_path.exists()
    reloaded = otio.adapters.read_from_file(str(otio_path))
    assert reloaded.name == "Episode_S01E01_Assembly"

    summary = timeline_to_summary_dict(timeline)
    assert summary["total_clips"] == 2
    assert summary["total_duration_seconds"] == 7.5
