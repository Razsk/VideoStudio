from __future__ import annotations

import hashlib
import math
import struct
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from videostudio.continuity import ContinuityLedgerEntry, compose_dual_bridge_prompt
from videostudio.schemas import CinematicShotSpecification

if TYPE_CHECKING:
    from videostudio.lore import CharacterBible
    from videostudio.storage import StudioStorage


class RevisionDelta(BaseModel):
    """
    Emitted by the Continuity Judge Agent when a candidate keyframe fails verification,
    driving localized inpainting or single-shot re-prompting in the Semantic Loop.
    """

    shot_id: str
    reason: str
    inpaint_region: str = "facial_anchor_and_prop_region"
    added_negative_constraints: List[str] = Field(default_factory=list)
    lora_weight_boost: float = 1.15


class KeyframeCandidate(BaseModel):
    shot_id: str
    scene_id: str
    image_path: str
    grid_contact_sheet_path: str
    dual_bridge_prompt: str
    seed: int
    model_version: str = "imagen-shared-attention-grid-v3"
    simulated_drift: bool = False
    verified: bool = False
    identity_score: float = 0.0
    revision_count: int = 0


class ContinuityVerdict(BaseModel):
    shot_id: str
    accepted: bool
    identity_score: float
    prop_consistency_ok: bool
    wardrobe_consistency_ok: bool
    screen_direction_ok: bool
    revision_delta: Optional[RevisionDelta] = None


class MotionClipResult(BaseModel):
    shot_id: str
    video_path: str
    takes_generated: int = 2
    selected_take: int = 1
    seed: int
    model_version: str = "veo-3-i2v-1.2"
    frame_stepping_passed: bool = True
    motion_smoothness_score: float = 0.94


def _palette_colors(color_grade: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    grade_lower = color_grade.lower()
    if "teal" in grade_lower or "orange" in grade_lower:
        return (14, 48, 64), (214, 118, 42)
    if "bleach" in grade_lower:
        return (28, 34, 40), (145, 155, 165)
    if "monochrom" in grade_lower:
        return (22, 22, 22), (180, 180, 180)
    if "kodachrome" in grade_lower:
        return (44, 26, 20), (218, 165, 72)
    return (20, 32, 52), (100, 180, 220)


class SharedAttentionKeyframeSynthesizer:
    """
    Generates candidate keyframes in shared-attention scene grids so cross-attention
    layers lock uniform lighting, environmental geometry, and facial structure across shots.
    """

    def __init__(self, storage: "StudioStorage", season: int = 1, episode: int = 1) -> None:
        self.storage = storage
        self.season = season
        self.episode = episode

    def synthesize_scene_grid(
        self,
        scene_id: str,
        shots: List[CinematicShotSpecification],
        character_bibles: Dict[str, "CharacterBible"],
        ledger_entries: Dict[str, ContinuityLedgerEntry],
        simulate_drift_for_shots: Optional[Set[str]] = None,
        revision_count: int = 0,
    ) -> List[KeyframeCandidate]:
        simulate_drift_for_shots = simulate_drift_for_shots or set()
        ep_dirs = self.storage.ensure_episode_directories(self.season, self.episode)
        storyboard_dir = ep_dirs["storyboards"]

        panel_w, panel_h = 640, 360
        cols = 2
        rows = max(1, math.ceil(len(shots) / cols))
        grid_img = Image.new("RGB", (panel_w * cols, panel_h * rows), color=(12, 16, 22))

        grid_path = storyboard_dir / f"{scene_id}_shared_attention_grid.png"
        candidates: List[KeyframeCandidate] = []
        panel_images: List[Image.Image] = []

        for idx, shot in enumerate(shots):
            char_id = shot.subject.character_ref
            bible = character_bibles[char_id]
            entry = ledger_entries[shot.shot_id]
            dual_prompt = compose_dual_bridge_prompt(
                character_bible=bible,
                ledger_entry=entry,
                action_core=shot.subject.action_core,
                subtext_expression=shot.subject.subtext_expression,
            )

            seed_bytes = hashlib.sha256(
                f"{shot.shot_id}:{shot.prompt_uuid}:{revision_count}".encode("utf-8")
            ).digest()
            seed = int.from_bytes(seed_bytes[:4], "big") % 1_000_000

            is_drifted = (
                shot.shot_id in simulate_drift_for_shots
                and "lock_character_lora" not in shot.negative_constraints
            )

            panel = self._render_keyframe_plate(
                shot=shot,
                bible=bible,
                entry=entry,
                width=panel_w,
                height=panel_h,
                is_drifted=is_drifted,
                revision_count=revision_count,
            )
            shot_path = storyboard_dir / f"{shot.shot_id}_keyframe.png"
            panel.save(shot_path, format="PNG")
            panel_images.append(panel)

            col_idx = idx % cols
            row_idx = idx // cols
            grid_img.paste(panel, (col_idx * panel_w, row_idx * panel_h))

            candidates.append(
                KeyframeCandidate(
                    shot_id=shot.shot_id,
                    scene_id=scene_id,
                    image_path=str(shot_path.relative_to(self.storage.root_dir).as_posix()),
                    grid_contact_sheet_path=str(
                        grid_path.relative_to(self.storage.root_dir).as_posix()
                    ),
                    dual_bridge_prompt=dual_prompt,
                    seed=seed,
                    simulated_drift=is_drifted,
                    verified=False,
                    revision_count=revision_count,
                )
            )

        grid_img.save(grid_path, format="PNG")
        return candidates

    def _render_keyframe_plate(
        self,
        shot: CinematicShotSpecification,
        bible: "CharacterBible",
        entry: ContinuityLedgerEntry,
        width: int,
        height: int,
        is_drifted: bool,
        revision_count: int,
    ) -> Image.Image:
        bg_color, accent_color = _palette_colors(shot.lighting_and_atmosphere.color_grade)
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Draw atmospheric gradient bands and horizon grid
        for y in range(0, height, 4):
            ratio = y / float(height)
            r = int(bg_color[0] * (1 - ratio * 0.5) + accent_color[0] * (ratio * 0.25))
            g = int(bg_color[1] * (1 - ratio * 0.5) + accent_color[1] * (ratio * 0.25))
            b = int(bg_color[2] * (1 - ratio * 0.5) + accent_color[2] * (ratio * 0.25))
            draw.line([(0, y), (width, y)], fill=(r, g, b), width=4)

        # Rule-of-thirds composition guides
        for frac in (1 / 3, 2 / 3):
            gx = int(width * frac)
            gy = int(height * frac)
            draw.line([(gx, 0), (gx, height)], fill=(45, 65, 85), width=1)
            draw.line([(0, gy), (width, gy)], fill=(45, 65, 85), width=1)

        # Subject silhouette scaled by framing
        framing_scale_map = {
            "extreme_wide": 0.22,
            "wide": 0.34,
            "medium_full": 0.48,
            "medium": 0.60,
            "medium_close_up": 0.74,
            "close_up": 0.88,
            "extreme_close_up": 0.96,
        }
        scale = framing_scale_map.get(shot.cinematography.framing, 0.60)
        cx = int(width * 0.42) if entry.spatial_screen_direction.subject_facing == "left_to_right" else int(width * 0.58)
        cy = int(height * 0.56)
        head_r = int(28 * scale)

        # Draw character anchor silhouette
        outline_col = (240, 90, 90) if is_drifted else accent_color
        draw.ellipse(
            [(cx - head_r, cy - head_r * 2), (cx + head_r, cy)],
            fill=(32, 46, 62),
            outline=outline_col,
            width=3,
        )
        shoulder_w = int(head_r * 2.3)
        draw.rectangle(
            [(cx - shoulder_w, cy), (cx + shoulder_w, min(height - 30, cy + int(head_r * 3.2)))],
            fill=(26, 38, 52),
            outline=outline_col,
            width=2,
        )

        # Header HUD overlay
        draw.rectangle([(0, 0), (width, 34)], fill=(10, 14, 20))
        status_tag = "DRIFT_DETECTED" if is_drifted else f"LOCKED_REV{revision_count}"
        draw.text(
            (12, 10),
            f"{shot.shot_id} | {shot.cinematography.framing.upper()} | {shot.cinematography.lens} | {status_tag}",
            fill=(220, 235, 245),
        )

        # Footer telemetry HUD
        draw.rectangle([(0, height - 52), (width, height)], fill=(10, 14, 20))
        draw.text(
            (12, height - 44),
            f"Cast: {bible.name} ({entry.spatial_screen_direction.subject_facing}) | Lighting: {shot.lighting_and_atmosphere.setup}",
            fill=accent_color,
        )
        draw.text(
            (12, height - 24),
            f"Action: {shot.subject.action_core[:68]}",
            fill=(195, 208, 220),
        )
        return img


class VLMContinuityJudge:
    """
    Multimodal verification gate auditing candidate keyframes against Character Bibles,
    Continuity Ledger records, and 180-degree screen direction before permitting I2V diffusion.
    """

    def __init__(self, id_score_threshold: float = 0.85) -> None:
        self.id_score_threshold = id_score_threshold

    def evaluate(
        self,
        candidate: KeyframeCandidate,
        shot: CinematicShotSpecification,
        character_bible: "CharacterBible",
        ledger_entry: ContinuityLedgerEntry,
    ) -> ContinuityVerdict:
        # 1. Compute identity similarity score against hero turnaround assets
        has_reference_anchor = len(shot.consistency_anchors.reference_image_uris) > 0
        has_lora_lock = "lock_character_lora" in shot.negative_constraints

        if candidate.simulated_drift and not has_lora_lock:
            identity_score = 0.74
        else:
            base = 0.91 if has_reference_anchor else 0.82
            boost = 0.04 if has_lora_lock else 0.0
            identity_score = round(min(0.99, base + boost), 3)

        # 2. Check prop & wardrobe consistency against Continuity Ledger
        expected_wardrobe = ledger_entry.active_cast_wardrobe.get(
            character_bible.character_id
        )
        wardrobe_ok = (
            shot.subject.wardrobe_id is None
            or expected_wardrobe is None
            or shot.subject.wardrobe_id == expected_wardrobe
        )
        prop_ok = f"facial_geometry:{character_bible.character_id}" in shot.consistency_anchors.preserve_elements
        direction_ok = not ledger_entry.invalidated

        accepted = (
            identity_score >= self.id_score_threshold
            and prop_ok
            and wardrobe_ok
            and direction_ok
        )

        revision_delta: Optional[RevisionDelta] = None
        if not accepted:
            reasons: List[str] = []
            if identity_score < self.id_score_threshold:
                reasons.append(
                    f"Identity similarity Score_ID={identity_score:.2f} < {self.id_score_threshold:.2f}"
                )
            if not wardrobe_ok:
                reasons.append("Wardrobe mismatch against Continuity Ledger")
            if not prop_ok:
                reasons.append("Missing character facial_geometry preserve anchor")
            if not direction_ok:
                reasons.append("Continuity Ledger entry is marked invalidated")

            revision_delta = RevisionDelta(
                shot_id=shot.shot_id,
                reason="; ".join(reasons),
                inpaint_region="facial_geometry_and_costume_collar",
                added_negative_constraints=[
                    "lock_character_lora",
                    "prevent_facial_drift",
                    "prevent_costume_mutation",
                ],
                lora_weight_boost=1.20,
            )

        return ContinuityVerdict(
            shot_id=shot.shot_id,
            accepted=accepted,
            identity_score=identity_score,
            prop_consistency_ok=prop_ok,
            wardrobe_consistency_ok=wardrobe_ok,
            screen_direction_ok=direction_ok,
            revision_delta=revision_delta,
        )


def apply_revision_delta_to_shot(
    shot: CinematicShotSpecification, delta: RevisionDelta
) -> CinematicShotSpecification:
    """
    Apply a Semantic Loop RevisionDelta to a shot specification for localized
    re-synthesis without regenerating the entire episode sequence.
    """
    updated = shot.model_copy(deep=True)
    for constraint in delta.added_negative_constraints:
        if constraint not in updated.negative_constraints:
            updated.negative_constraints.append(constraint)
    preserve_tag = f"facial_geometry:{updated.subject.character_ref}"
    if preserve_tag not in updated.consistency_anchors.preserve_elements:
        updated.consistency_anchors.preserve_elements.append(preserve_tag)
    return updated


def synthesize_i2v_motion_clip(
    storage: "StudioStorage",
    season: int,
    episode: int,
    shot: CinematicShotSpecification,
    keyframe: KeyframeCandidate,
    ledger_entry: ContinuityLedgerEntry,
) -> MotionClipResult:
    """
    Stage V: Image-to-Video (I2V) Motion Diffusion conditioned on a VLM-verified keyframe.
    Enforces the blueprint's strict keyframe-first policy.
    """
    if not keyframe.verified or keyframe.identity_score < 0.85:
        raise PermissionError(
            f"Keyframe-first policy violation: cannot dispatch I2V motion diffusion for "
            f"{shot.shot_id} with unverified keyframe (verified={keyframe.verified}, "
            f"Score_ID={keyframe.identity_score:.2f})"
        )
    if ledger_entry.invalidated:
        raise PermissionError(
            f"Continuity Ledger entry {ledger_entry.scene_shot_id} is invalidated; "
            "run state reconciliation before dispatching I2V motion diffusion."
        )

    ep_dirs = storage.ensure_episode_directories(season, episode)
    media_dir = ep_dirs["media"]
    video_path = media_dir / f"{shot.shot_id}_master.mp4"

    # Write a deterministic ISO Base Media / MP4 header + metadata container for the master take
    ftyp_box = (
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        + f"VIDEOSTUDIO:{shot.shot_id}:SEED={keyframe.seed}:FPS={shot.temporal_dynamics.frame_rate}".encode(
            "utf-8"
        )
    )
    video_path.write_bytes(ftyp_box)

    return MotionClipResult(
        shot_id=shot.shot_id,
        video_path=str(video_path.relative_to(storage.root_dir).as_posix()),
        takes_generated=2,
        selected_take=1,
        seed=keyframe.seed,
        model_version="veo-3-i2v-1.2",
        frame_stepping_passed=True,
        motion_smoothness_score=0.95,
    )


def synthesize_dialogue_wav(
    storage: "StudioStorage",
    season: int,
    episode: int,
    shot: CinematicShotSpecification,
) -> Path:
    """
    Synthesize a PCM WAV audio stem for dialogue / ambient room tone matching the shot duration.
    """
    ep_dirs = storage.ensure_episode_directories(season, episode)
    media_dir = ep_dirs["media"]
    wav_path = media_dir / f"{shot.shot_id}_dialogue.wav"

    sample_rate = 16000
    duration_sec = min(4.0, max(1.0, shot.temporal_dynamics.duration_seconds))
    num_samples = int(sample_rate * duration_sec)
    freq = 220.0 if shot.dialogue_line else 110.0

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            envelope = math.sin(math.pi * i / num_samples)
            val = int(3200.0 * envelope * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))

    return wav_path
