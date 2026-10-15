from pathlib import Path

import pytest

from videostudio.continuity import (
    ContinuityLedger,
    ContinuityLedgerEntry,
    SpatialScreenDirection,
    compose_dual_bridge_prompt,
)
from videostudio.lore import seed_default_canon
from videostudio.storage import StudioStorage


def test_continuity_ledger_carries_forward_trauma_props_and_persists_parquet(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    seed_default_canon(storage)

    ledger = ContinuityLedger(episode_id="S01E01")
    e1 = ledger.append_shot_state(
        scene_shot_id="SC01_SH01",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={"CHAR_ELENA_VANCE": ["rain_drenched", "breath_misting"]},
        prop_registry_affordance={"ART_CHRONO_COMPASS": "closed_on_belt"},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_DOME_CONSOLE",
            camera_side="north_of_axis",
            subject_facing="left_to_right",
            eyeline_vector="east_15deg_up",
        ),
        lighting_environmental={
            "time_of_day": "NIGHT",
            "solar_angle": "lunar_zenith",
            "weather": "subpolar_sleet",
            "lighting_setup": "Chiaroscuro",
        },
        causal_reveal_flags=["BEACON_9_SIGNAL_DETECTED"],
    )
    assert e1.ledger_index == 0

    # Appending SC01_SH02 automatically inherits progressive physical state, props, and reveal flags
    e2 = ledger.append_shot_state(
        scene_shot_id="SC01_SH02",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={"CHAR_ELENA_VANCE": ["cut_right_knuckle"]},
        prop_registry_affordance={"ART_CHRONO_COMPASS": "opened_glowing"},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_DOME_CONSOLE",
            camera_side="north_of_axis",
            subject_facing="left_to_right",
            eyeline_vector="east_15deg_up",
        ),
        lighting_environmental={},  # Inherits locked scene lighting from SC01_SH01
        causal_reveal_flags=["SECTOR_4_OVERRIDE_UNLOCKED"],
    )

    assert "rain_drenched" in e2.dynamic_physical_state["CHAR_ELENA_VANCE"]
    assert "cut_right_knuckle" in e2.dynamic_physical_state["CHAR_ELENA_VANCE"]
    assert e2.prop_registry_affordance["ART_CHRONO_COMPASS"] == "opened_glowing"
    assert "BEACON_9_SIGNAL_DETECTED" in e2.causal_reveal_flags
    assert "SECTOR_4_OVERRIDE_UNLOCKED" in e2.causal_reveal_flags
    assert e2.lighting_environmental["lighting_setup"] == "Chiaroscuro"

    # Persist to Parquet & reload
    parquet_path = ledger.save_parquet(storage, season=1, episode=1)
    assert parquet_path.exists()
    assert parquet_path.suffix == ".parquet"

    reloaded = ContinuityLedger.load_parquet(parquet_path, episode_id="S01E01")
    assert len(reloaded.entries) == 2
    assert reloaded.entries[1].prop_registry_affordance["ART_CHRONO_COMPASS"] == "opened_glowing"


def test_continuity_ledger_upstream_invalidation_and_reconciliation():
    ledger = ContinuityLedger(episode_id="S01E01")
    ledger.append_shot_state(
        scene_shot_id="SC01_SH01",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={"CHAR_ELENA_VANCE": ["nominal"]},
        prop_registry_affordance={"ART_CHRONO_COMPASS": "closed"},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_01",
            camera_side="north_of_axis",
            subject_facing="left_to_right",
            eyeline_vector="east",
        ),
        lighting_environmental={"time_of_day": "NIGHT", "lighting_setup": "Chiaroscuro"},
        causal_reveal_flags=[],
    )
    ledger.append_shot_state(
        scene_shot_id="SC01_SH02",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={},
        prop_registry_affordance={},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_01",
            camera_side="north_of_axis",
            subject_facing="left_to_right",
            eyeline_vector="east",
        ),
        lighting_environmental={},
        causal_reveal_flags=[],
    )
    ledger.append_shot_state(
        scene_shot_id="SC02_SH01",
        active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
        dynamic_physical_state={},
        prop_registry_affordance={},
        spatial_screen_direction=SpatialScreenDirection(
            axis_id="AXIS_02",
            camera_side="west_of_axis",
            subject_facing="right_to_left",
            eyeline_vector="south",
        ),
        lighting_environmental={"time_of_day": "NIGHT", "lighting_setup": "Volumetric Split"},
        causal_reveal_flags=[],
    )

    # Mutate SC01_SH01 upstream -> invalidates SC01_SH02 and SC02_SH01
    invalidated_ids = ledger.mutate_upstream_entry(
        scene_shot_id="SC01_SH01",
        added_physical_state={"CHAR_ELENA_VANCE": ["shoulder_frostbite"]},
        updated_props={"ART_CHRONO_COMPASS": "cracked_lens"},
        added_reveal_flags=["SECRET_GHOST_TELEMETRY"],
    )
    assert invalidated_ids == ["SC01_SH02", "SC02_SH01"]
    assert ledger.get_entry("SC01_SH02").invalidated is True
    assert ledger.get_entry("SC02_SH01").invalidated is True

    # Reconcile state graph -> propagates mutations downstream and clears invalidated flags
    reconciled = ledger.reconcile_state_graph()
    assert reconciled == ["SC01_SH02", "SC02_SH01"]
    e3 = ledger.get_entry("SC02_SH01")
    assert e3.invalidated is False
    assert "shoulder_frostbite" in e3.dynamic_physical_state["CHAR_ELENA_VANCE"]
    assert e3.prop_registry_affordance["ART_CHRONO_COMPASS"] == "cracked_lens"
    assert "SECRET_GHOST_TELEMETRY" in e3.causal_reveal_flags


def test_180_degree_rule_violation_detection_and_dual_bridge_prompt(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    seed_default_canon(storage)
    elena = storage.load_character_bible("CHAR_ELENA_VANCE")

    ledger = ContinuityLedger(episode_id="S01E01")
    e1 = ledger.append_shot_state(
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
        causal_reveal_flags=[],
    )

    # Crossing the 180-degree axis in the same scene without a motivating camera movement
    with pytest.raises(ValueError, match="180-degree axis violation"):
        ledger.append_shot_state(
            scene_shot_id="SC01_SH02",
            active_cast_wardrobe={"CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH"},
            dynamic_physical_state={},
            prop_registry_affordance={},
            spatial_screen_direction=SpatialScreenDirection(
                axis_id="AXIS_DOME",
                camera_side="south_of_axis",  # Crossed axis!
                subject_facing="right_to_left",
                eyeline_vector="west",
            ),
            lighting_environmental={},
            causal_reveal_flags=[],
            enforce_180_rule=True,
        )

    prompt = compose_dual_bridge_prompt(
        character_bible=elena,
        ledger_entry=e1,
        action_core="Elena aligns the brass azimuth vernier",
        subtext_expression="Eyes narrowed against the console glare",
    )
    assert "[IDENTITY_ANCHOR:CHAR_ELENA_VANCE" in prompt
    assert "[DYNAMIC_SCENE_STATE:SC01_SH01" in prompt
    assert "Weathered navy pressure-trench" in prompt
    assert "rain_drenched" in prompt
