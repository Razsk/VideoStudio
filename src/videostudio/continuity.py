from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from videostudio.lore import CharacterBible
    from videostudio.storage import StudioStorage


class SpatialScreenDirection(BaseModel):
    """Tracks camera side of the 180-degree action axis, subject facing, and eye-line vector."""

    axis_id: str = "AXIS_DEFAULT"
    camera_side: str = "north_of_axis"
    subject_facing: str = "left_to_right"
    eyeline_vector: str = "level_center"
    axis_reestablished_by_movement: bool = False


class ContinuityLedgerEntry(BaseModel):
    """
    Single row in the append-only Continuity Ledger tracking the 7 canonical columns
    specified in the Architectural Blueprint.
    """

    ledger_index: int
    scene_shot_id: str
    active_cast_wardrobe: Dict[str, str] = Field(default_factory=dict)
    dynamic_physical_state: Dict[str, List[str]] = Field(default_factory=dict)
    prop_registry_affordance: Dict[str, str] = Field(default_factory=dict)
    spatial_screen_direction: SpatialScreenDirection
    lighting_environmental: Dict[str, str] = Field(default_factory=dict)
    causal_reveal_flags: List[str] = Field(default_factory=list)
    invalidated: bool = False

    @property
    def scene_id(self) -> str:
        return self.scene_shot_id.split("_", 1)[0]


class ContinuityLedger:
    """
    Explicit, append-only state graph tracking the physical and narrative status of all
    assets across sequential shots, persisted to Apache Parquet and JSON.
    """

    def __init__(self, episode_id: str = "S01E01") -> None:
        self.episode_id = episode_id
        self._entries: List[ContinuityLedgerEntry] = []

    @property
    def entries(self) -> List[ContinuityLedgerEntry]:
        return self._entries

    def get_entry(self, scene_shot_id: str) -> ContinuityLedgerEntry:
        for entry in self._entries:
            if entry.scene_shot_id == scene_shot_id:
                return entry
        raise KeyError(f"Shot {scene_shot_id} not found in ContinuityLedger")

    def append_shot_state(
        self,
        scene_shot_id: str,
        active_cast_wardrobe: Dict[str, str],
        dynamic_physical_state: Dict[str, List[str]],
        prop_registry_affordance: Dict[str, str],
        spatial_screen_direction: SpatialScreenDirection,
        lighting_environmental: Dict[str, str],
        causal_reveal_flags: List[str],
        enforce_180_rule: bool = True,
    ) -> ContinuityLedgerEntry:
        prev = self._entries[-1] if self._entries else None
        current_scene_id = scene_shot_id.split("_", 1)[0]

        # 1. Validate 180-degree cinematic rule within continuous scenes
        if (
            enforce_180_rule
            and prev is not None
            and prev.scene_id == current_scene_id
            and prev.spatial_screen_direction.axis_id == spatial_screen_direction.axis_id
            and prev.spatial_screen_direction.camera_side != spatial_screen_direction.camera_side
            and not spatial_screen_direction.axis_reestablished_by_movement
        ):
            raise ValueError(
                f"180-degree axis violation between {prev.scene_shot_id} "
                f"({prev.spatial_screen_direction.camera_side}) and {scene_shot_id} "
                f"({spatial_screen_direction.camera_side}) on axis {spatial_screen_direction.axis_id}"
            )

        # 2. Carry forward wardrobe within same scene if not explicitly overridden
        merged_wardrobe: Dict[str, str] = {}
        if prev is not None and prev.scene_id == current_scene_id:
            merged_wardrobe.update(prev.active_cast_wardrobe)
        merged_wardrobe.update(active_cast_wardrobe)

        # 3. Carry progressive physical state (wounds, sweat, grime, fatigue) forward
        merged_physical: Dict[str, List[str]] = {}
        if prev is not None:
            for char_id, states in prev.dynamic_physical_state.items():
                merged_physical[char_id] = list(states)
        for char_id, new_states in dynamic_physical_state.items():
            existing = merged_physical.setdefault(char_id, [])
            for st in new_states:
                if st not in existing:
                    existing.append(st)

        # 4. Carry prop registry & affordances forward
        merged_props: Dict[str, str] = {}
        if prev is not None:
            merged_props.update(prev.prop_registry_affordance)
        merged_props.update(prop_registry_affordance)

        # 5. Lock lighting & environmental profile within the same scene
        merged_lighting: Dict[str, str] = {}
        if prev is not None and prev.scene_id == current_scene_id:
            merged_lighting.update(prev.lighting_environmental)
        merged_lighting.update(lighting_environmental)

        # 6. Carry causal reveal flags forward monotonically
        merged_flags: List[str] = list(prev.causal_reveal_flags) if prev is not None else []
        for flag in causal_reveal_flags:
            if flag not in merged_flags:
                merged_flags.append(flag)

        entry = ContinuityLedgerEntry(
            ledger_index=len(self._entries),
            scene_shot_id=scene_shot_id,
            active_cast_wardrobe=merged_wardrobe,
            dynamic_physical_state=merged_physical,
            prop_registry_affordance=merged_props,
            spatial_screen_direction=spatial_screen_direction,
            lighting_environmental=merged_lighting,
            causal_reveal_flags=merged_flags,
            invalidated=False,
        )
        self._entries.append(entry)
        return entry

    def mutate_upstream_entry(
        self,
        scene_shot_id: str,
        added_physical_state: Optional[Dict[str, List[str]]] = None,
        updated_props: Optional[Dict[str, str]] = None,
        added_reveal_flags: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Modify an upstream entry in the state graph and invalidate all subsequent
        downstream shot nodes, forcing a reconciliation pass before video dispatch.
        """
        target_idx: Optional[int] = None
        for idx, entry in enumerate(self._entries):
            if entry.scene_shot_id == scene_shot_id:
                target_idx = idx
                break
        if target_idx is None:
            raise KeyError(f"Upstream shot {scene_shot_id} not found in ContinuityLedger")

        target = self._entries[target_idx]
        if added_physical_state:
            for char_id, states in added_physical_state.items():
                existing = target.dynamic_physical_state.setdefault(char_id, [])
                for st in states:
                    if st not in existing:
                        existing.append(st)
        if updated_props:
            target.prop_registry_affordance.update(updated_props)
        if added_reveal_flags:
            for flag in added_reveal_flags:
                if flag not in target.causal_reveal_flags:
                    target.causal_reveal_flags.append(flag)

        invalidated_ids: List[str] = []
        for downstream in self._entries[target_idx + 1 :]:
            downstream.invalidated = True
            invalidated_ids.append(downstream.scene_shot_id)
        return invalidated_ids

    def reconcile_state_graph(self) -> List[str]:
        """
        Propagate physical state, prop affordances, scene-locked lighting, and causal
        reveal flags across all invalidated downstream nodes and clear their invalidation flag.
        """
        reconciled_ids: List[str] = []
        for idx in range(1, len(self._entries)):
            prev = self._entries[idx - 1]
            curr = self._entries[idx]
            if not curr.invalidated:
                continue

            for char_id, states in prev.dynamic_physical_state.items():
                existing = curr.dynamic_physical_state.setdefault(char_id, [])
                for st in states:
                    if st not in existing:
                        existing.append(st)

            for prop_id, prop_state in prev.prop_registry_affordance.items():
                curr.prop_registry_affordance[prop_id] = prop_state

            if prev.scene_id == curr.scene_id:
                for k, v in prev.lighting_environmental.items():
                    curr.lighting_environmental.setdefault(k, v)

            for flag in prev.causal_reveal_flags:
                if flag not in curr.causal_reveal_flags:
                    curr.causal_reveal_flags.append(flag)

            curr.invalidated = False
            reconciled_ids.append(curr.scene_shot_id)
        return reconciled_ids

    # ------------------------------------------------------------------
    # Parquet & JSON Serialization
    # ------------------------------------------------------------------

    def to_pyarrow_table(self) -> pa.Table:
        rows = {
            "ledger_index": [e.ledger_index for e in self._entries],
            "scene_shot_id": [e.scene_shot_id for e in self._entries],
            "active_cast_wardrobe": [
                json.dumps(e.active_cast_wardrobe, sort_keys=True) for e in self._entries
            ],
            "dynamic_physical_state": [
                json.dumps(e.dynamic_physical_state, sort_keys=True) for e in self._entries
            ],
            "prop_registry_affordance": [
                json.dumps(e.prop_registry_affordance, sort_keys=True) for e in self._entries
            ],
            "spatial_screen_direction": [
                json.dumps(e.spatial_screen_direction.model_dump(), sort_keys=True)
                for e in self._entries
            ],
            "lighting_environmental": [
                json.dumps(e.lighting_environmental, sort_keys=True) for e in self._entries
            ],
            "causal_reveal_flags": [
                json.dumps(e.causal_reveal_flags) for e in self._entries
            ],
            "invalidated": [e.invalidated for e in self._entries],
        }
        return pa.Table.from_pydict(rows)

    def save_parquet(
        self, storage: "StudioStorage", season: int, episode: int
    ) -> Path:
        ep_dirs = storage.ensure_episode_directories(season, episode)
        parquet_path = ep_dirs["continuity"] / "continuity_ledger.parquet"
        json_path = ep_dirs["continuity"] / "continuity_ledger.json"

        table = self.to_pyarrow_table()
        pq.write_table(table, parquet_path)
        json_path.write_text(
            json.dumps([e.model_dump() for e in self._entries], indent=2),
            encoding="utf-8",
        )
        return parquet_path

    @classmethod
    def load_parquet(
        cls, parquet_path: Path | str, episode_id: str = "S01E01"
    ) -> "ContinuityLedger":
        table = pq.read_table(parquet_path)
        pydict = table.to_pydict()
        ledger = cls(episode_id=episode_id)
        num_rows = len(pydict.get("scene_shot_id", []))
        for i in range(num_rows):
            entry = ContinuityLedgerEntry(
                ledger_index=pydict["ledger_index"][i],
                scene_shot_id=pydict["scene_shot_id"][i],
                active_cast_wardrobe=json.loads(pydict["active_cast_wardrobe"][i]),
                dynamic_physical_state=json.loads(pydict["dynamic_physical_state"][i]),
                prop_registry_affordance=json.loads(pydict["prop_registry_affordance"][i]),
                spatial_screen_direction=SpatialScreenDirection.model_validate(
                    json.loads(pydict["spatial_screen_direction"][i])
                ),
                lighting_environmental=json.loads(pydict["lighting_environmental"][i]),
                causal_reveal_flags=json.loads(pydict["causal_reveal_flags"][i]),
                invalidated=pydict["invalidated"][i],
            )
            ledger._entries.append(entry)
        return ledger


def compose_dual_bridge_prompt(
    character_bible: "CharacterBible",
    ledger_entry: ContinuityLedgerEntry,
    action_core: str,
    subtext_expression: str,
) -> str:
    """
    Dual-Bridge Consistency Prompt Composer:
    Extracts frozen invariant traits from the Character Bible and appends ONLY the
    variable Dynamic Scene State from the Continuity Ledger, preventing diffusion models
    from re-interpreting base facial anatomy when introducing narrative modifications.
    """
    char_id = character_bible.character_id
    invariant_anchor = character_bible.compose_invariant_anchor_prompt()

    wardrobe_id = ledger_entry.active_cast_wardrobe.get(char_id, "DEFAULT_COSTUME")
    wardrobe_desc = character_bible.costume_variants.get(wardrobe_id, wardrobe_id)
    physical_conditions = ", ".join(
        ledger_entry.dynamic_physical_state.get(char_id, ["nominal"])
    )
    active_props = ", ".join(
        f"{k}:{v}" for k, v in ledger_entry.prop_registry_affordance.items()
    )
    lighting_str = ", ".join(
        f"{k}={v}" for k, v in ledger_entry.lighting_environmental.items()
    )
    direction = ledger_entry.spatial_screen_direction

    dynamic_bridge = (
        f"[DYNAMIC_SCENE_STATE:{ledger_entry.scene_shot_id} | "
        f"Wardrobe({wardrobe_id}): {wardrobe_desc} | "
        f"PhysicalCondition: {physical_conditions} | "
        f"Props: {active_props or 'none'} | "
        f"ScreenDirection: {direction.subject_facing} ({direction.camera_side}, eyeline {direction.eyeline_vector}) | "
        f"LightingLock: {lighting_str} | "
        f"Action: {action_core} | "
        f"MicroExpression: {subtext_expression}]"
    )
    return f"{invariant_anchor} {dynamic_bridge}"
