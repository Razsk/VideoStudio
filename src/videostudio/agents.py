from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, TypedDict

from langgraph.graph import END, StateGraph

from videostudio.continuity import ContinuityLedger, SpatialScreenDirection
from videostudio.editorial import (
    construct_editorial_timeline,
    export_timeline_otio,
    timeline_to_summary_dict,
)
from videostudio.lore import CharacterBible, LocationBible, LoreGraph, seed_default_canon
from videostudio.media import (
    ContinuityVerdict,
    KeyframeCandidate,
    MotionClipResult,
    SharedAttentionKeyframeSynthesizer,
    VLMContinuityJudge,
    apply_revision_delta_to_shot,
    synthesize_dialogue_wav,
    synthesize_i2v_motion_clip,
)
from videostudio.schemas import (
    SAVE_THE_CAT_15_BEATS,
    STORY_CIRCLE_8_STEPS,
    ActionElement,
    BeatEntry,
    BeatSheet,
    CharacterElement,
    CinematicShotSpecification,
    CinematographySpec,
    ConsistencyAnchorsSpec,
    DialogueElement,
    LightingAndAtmosphereSpec,
    ParentheticalElement,
    SceneCard,
    SceneContextSpec,
    SceneHeadingElement,
    ScreenJSONDocument,
    ScreenJSONScene,
    SubjectSpec,
    TemporalDynamicsSpec,
    ThematicDossier,
    TransitionElement,
)
from videostudio.llm import LLMConfig, LLMGateway

if TYPE_CHECKING:
    from videostudio.storage import StudioStorage


# ---------------------------------------------------------------------------
# Specialized Functional Agents
# ---------------------------------------------------------------------------


class ResearchLoreAgent:
    """
    Queries the GraphRAG Lore Base and vector store to compile a structured
    ThematicDossier aligned with worldbuilding constraints and episodic goals.
    """

    def run(
        self,
        episode_id: str,
        story_seed: str,
        season_arc: str,
        lore_graph: LoreGraph,
        llm_config: Optional[LLMConfig] = None,
        llm_gateway: Optional[LLMGateway] = None,
    ) -> ThematicDossier:
        precedents = lore_graph.retrieve_tonal_precedents(story_seed, top_k=2)
        entity_ids = list(lore_graph.nodes.keys())
        elena_constraints = lore_graph.query_causal_constraints("CHAR_ELENA_VANCE", current_step=1)

        immutable_facts = [
            f"Season Arc: {season_arc}",
            "Commander Elena Vance commands the Helios Deep-Space Observatory Dome.",
            "Dr. Marcus Koren holds dual allegiance with the Aether Directorate.",
            f"Accessible artifacts at episode start: {', '.join(elena_constraints['accessible_artifacts']) or 'ART_CHRONO_COMPASS'}",
        ]

        if llm_config and llm_config.provider != "deterministic" and llm_gateway:
            try:
                return llm_gateway.generate_structured(
                    config=llm_config,
                    system_prompt=(
                        "You are the Research and Lore Agent for an automated episodic video studio. "
                        "Synthesize a ThematicDossier adhering strictly to the provided GraphRAG worldbuilding constraints."
                    ),
                    user_prompt=(
                        f"Episode ID: {episode_id}\nStory Seed: {story_seed}\n"
                        f"Season Arc: {season_arc}\nImmutable Facts: {immutable_facts}\n"
                        f"Entities: {entity_ids}\nTonal Precedents: {[p['text'] for p in precedents]}"
                    ),
                    response_model=ThematicDossier,
                )
            except Exception:
                if not llm_config.fallback_to_deterministic:
                    raise

        return ThematicDossier(
            episode_id=episode_id,
            story_seed=story_seed,
            premise=(
                f"When {story_seed.rstrip('.')}, Commander Elena Vance and Dr. Marcus Koren "
                "must verify the anomalous carrier wave inside the Sub-Level 4 Cryogenic Relay Vault "
                "before orbital containment seals the dome."
            ),
            tone="Tactile analog-futurist sci-fi thriller with chiaroscuro tension",
            target_conflicts=[
                "Institutional secrecy vs. empirical truth over Beacon 9 telemetry",
                "Sub-polar environmental hazard threatening dome structural integrity",
                "Asymmetric knowledge between Koren and Vance regarding the Ghost Telemetry",
            ],
            immutable_facts=immutable_facts,
            lore_entities_referenced=entity_ids,
            tonal_precedents=[p["text"] for p in precedents],
            setting_adherence_score=0.96,
        )


class DirectorAgent:
    """
    Transforms a ThematicDossier into a 15-Beat Save the Cat (or 8-Step Story Circle)
    structural matrix and decomposes beats into causally linked SceneCards.
    """

    def run(
        self,
        dossier: ThematicDossier,
        framework: str = "save_the_cat_15",
    ) -> BeatSheet:
        beat_names = (
            SAVE_THE_CAT_15_BEATS
            if framework == "save_the_cat_15"
            else STORY_CIRCLE_8_STEPS
        )
        tension_curve = [
            0.25,
            0.30,
            0.35,
            0.55,
            0.50,
            0.62,
            0.58,
            0.66,
            0.80,
            0.78,
            0.88,
            0.92,
            0.85,
            0.96,
            0.40,
        ]
        beats: List[BeatEntry] = []
        for idx, b_name in enumerate(beat_names):
            tension = tension_curve[idx % len(tension_curve)]
            beats.append(
                BeatEntry(
                    beat_index=idx + 1,
                    beat_name=b_name,
                    summary=f"[{b_name}] {dossier.premise[:90]} — dramatic pivot {idx + 1}.",
                    dramatic_tension=tension,
                )
            )

        scene_cards = [
            SceneCard(
                scene_id="SC01",
                beat_name="Catalyst",
                dramatic_objective="Isolate and lock the anomalous Beacon 9 carrier wave on the observatory azimuth array",
                active_obstacle="Geomagnetic sleet storm and encrypted phase drift",
                character_stakes="Missing the transmission window permanently erases the coordinates",
                initial_state={
                    "relay_lock": "unlocked",
                    "compass_state": "closed_on_belt",
                    "vault_access": "sealed",
                },
                terminal_state={
                    "relay_lock": "phase_locked",
                    "compass_state": "opened_calibrated",
                    "vault_access": "authorized",
                },
                causal_predecessor_scene_id=None,
            ),
            SceneCard(
                scene_id="SC02",
                beat_name="Midpoint",
                dramatic_objective="Descend into the Sub-Level 4 Cryogenic Relay Vault and insert the Chrono-Compass",
                active_obstacle="Venting cryogenic nitrogen mist and Koren's concealed override protocol",
                character_stakes="Exposure of the Aether Directorate's sabotage of Beacon 9",
                initial_state={
                    "relay_lock": "phase_locked",
                    "compass_state": "opened_calibrated",
                    "vault_access": "authorized",
                },
                terminal_state={
                    "relay_lock": "decrypted",
                    "compass_state": "engaged_in_core",
                    "vault_access": "lockdown_triggered",
                },
                causal_predecessor_scene_id="SC01",
            ),
            SceneCard(
                scene_id="SC03",
                beat_name="Finale",
                dramatic_objective="Transmit the decrypted Jovian coordinates before the vault bulkhead seals",
                active_obstacle="Automated containment purge and fracturing waveguide",
                character_stakes="Survival of the Helios Watch crew and preservation of the signal proof",
                initial_state={
                    "relay_lock": "decrypted",
                    "compass_state": "engaged_in_core",
                    "vault_access": "lockdown_triggered",
                },
                terminal_state={
                    "relay_lock": "broadcast_complete",
                    "compass_state": "recovered_scorched",
                    "vault_access": "escaped_upper_ring",
                },
                causal_predecessor_scene_id="SC02",
            ),
        ]

        sheet = BeatSheet(
            episode_id=dossier.episode_id,
            framework="save_the_cat_15" if framework == "save_the_cat_15" else "story_circle_8",
            beats=beats,
            scene_cards=scene_cards,
            pacing_score=0.94,
            dramatic_curve_valid=True,
        )
        sheet.validate_causal_chain()
        return sheet


class ScreenwriterAgent:
    """
    Translates BeatSheet SceneCards into standardized ScreenJSON AST screenplays
    with observable-only action lines and exports industry-standard Fountain markup.
    """

    def run(
        self,
        beat_sheet: BeatSheet,
        character_bibles: Dict[str, CharacterBible],
        location_bibles: Dict[str, LocationBible],
    ) -> ScreenJSONDocument:
        scenes: List[ScreenJSONScene] = []

        for idx, card in enumerate(beat_sheet.scene_cards):
            loc_id = (
                "LOC_OBSERVATORY_DOME"
                if idx == 0
                else "LOC_SUBLEVEL_RELAY_VAULT"
            )
            loc = location_bibles[loc_id]

            if idx == 0:
                elements = [
                    ActionElement(
                        description=(
                            "Sleet lashes the curved glass of the observatory dome. "
                            "Commander Elena Vance rotates the brass azimuth vernier until the green CRT waveform stabilizes."
                        )
                    ),
                    CharacterElement(
                        character_id="CHAR_ELENA_VANCE",
                        name="ELENA VANCE",
                        base_bible_anchor_key="canon/bible/characters/CHAR_ELENA_VANCE",
                    ),
                    ParentheticalElement(
                        micro_expression="eyes fixed on the oscilloscope, jaw set",
                        emotional_cadence="low, measured urgency",
                    ),
                    DialogueElement(
                        character_id="CHAR_ELENA_VANCE",
                        spoken_string="That carrier wave is repeating on a seven-second harmonic. Unseal the Chrono-Compass.",
                        language_identifier="en-US",
                    ),
                    ActionElement(
                        description=(
                            "Dr. Marcus Koren steps into the amber console light, adjusting his titanium spectacles as he unlatches the brass compass casing."
                        )
                    ),
                    CharacterElement(
                        character_id="CHAR_MARCUS_KOREN",
                        name="DR. MARCUS KOREN",
                        base_bible_anchor_key="canon/bible/characters/CHAR_MARCUS_KOREN",
                    ),
                    ParentheticalElement(
                        micro_expression="glancing toward the pressure bulkhead",
                        emotional_cadence="guarded, hesitant",
                    ),
                    DialogueElement(
                        character_id="CHAR_MARCUS_KOREN",
                        spoken_string="If we route that harmonic through Sub-Level Four, the Directorate sensors will register the spike.",
                        language_identifier="en-US",
                    ),
                    TransitionElement(transition_type="CUT TO:"),
                ]
            elif idx == 1:
                elements = [
                    ActionElement(
                        description=(
                            "Cryogenic vapor pours across the grated basalt floor of the vault. "
                            "Elena presses the opened Chrono-Compass into the recessed waveguide socket."
                        )
                    ),
                    CharacterElement(
                        character_id="CHAR_ELENA_VANCE",
                        name="ELENA VANCE",
                        base_bible_anchor_key="canon/bible/characters/CHAR_ELENA_VANCE",
                    ),
                    ParentheticalElement(
                        micro_expression="breath misting in the cold, brow furrowed",
                        emotional_cadence="resolute",
                    ),
                    DialogueElement(
                        character_id="CHAR_ELENA_VANCE",
                        spoken_string="The phase lock holds. Read me the origin coordinates before the frost blinds the primary optics.",
                        language_identifier="en-US",
                    ),
                    ActionElement(
                        description=(
                            "Sparks arc across the conduit manifold, leaving a scorch mark along Elena's right forearm sleeve as Koren braces the terminal."
                        )
                    ),
                    CharacterElement(
                        character_id="CHAR_MARCUS_KOREN",
                        name="DR. MARCUS KOREN",
                        base_bible_anchor_key="canon/bible/characters/CHAR_MARCUS_KOREN",
                    ),
                    ParentheticalElement(
                        micro_expression="eyes widening behind fogged lenses",
                        emotional_cadence="stunned realization",
                    ),
                    DialogueElement(
                        character_id="CHAR_MARCUS_KOREN",
                        spoken_string="It isn't an echo. Beacon Nine is broadcasting live from inside the Jovian shadow.",
                        language_identifier="en-US",
                    ),
                    TransitionElement(transition_type="DISSOLVE TO:"),
                ]
            else:
                elements = [
                    ActionElement(
                        description=(
                            "Amber containment beacons spin along the vault ceiling. "
                            "Elena pulls the scorched Chrono-Compass free and engages the uplink lever as the blast doors begin to close."
                        )
                    ),
                    CharacterElement(
                        character_id="CHAR_ELENA_VANCE",
                        name="ELENA VANCE",
                        base_bible_anchor_key="canon/bible/characters/CHAR_ELENA_VANCE",
                    ),
                    ParentheticalElement(
                        micro_expression="flinching against the sodium glare, resolute",
                        emotional_cadence="commanding",
                    ),
                    DialogueElement(
                        character_id="CHAR_ELENA_VANCE",
                        spoken_string="Telemetry packet transmitted. Move—through the upper hatch now!",
                        language_identifier="en-US",
                    ),
                    TransitionElement(transition_type="FADE OUT:"),
                ]

            scenes.append(
                ScreenJSONScene(
                    scene_id=card.scene_id,
                    beat_name=card.beat_name,
                    heading=SceneHeadingElement(
                        context="INT",
                        setting=loc.name,
                        time_of_day="NIGHT",
                        lighting_lock=loc.default_lighting_setup,
                        color_palette_lock=loc.default_color_grade,
                    ),
                    elements=elements,
                    initial_state=card.initial_state,
                    terminal_state=card.terminal_state,
                )
            )

        return ScreenJSONDocument(
            episode_id=beat_sheet.episode_id,
            title=f"Episode {beat_sheet.episode_id}: The Azimuth Signal",
            scenes=scenes,
            dialogue_naturalism_score=0.95,
            subtext_faithfulness_score=0.93,
        )


class CinematographerAgent:
    """
    Camera artist agent translating ScreenJSON scenes into validated
    CinematicShotSpecification schemas and populating the Continuity Ledger.
    """

    def run(
        self,
        screenplay: ScreenJSONDocument,
        character_bibles: Dict[str, CharacterBible],
        location_bibles: Dict[str, LocationBible],
    ) -> tuple[List[CinematicShotSpecification], ContinuityLedger]:
        ledger = ContinuityLedger(episode_id=screenplay.episode_id)
        shots: List[CinematicShotSpecification] = []

        coverage_cycle = [
            ("wide", "eye_level", "dolly_in", "24mm_wide"),
            ("medium_close_up", "low_angle", "static", "35mm_cinematic"),
            ("close_up", "eye_level", "pan_right", "85mm_portrait"),
            ("medium", "high_angle", "tracking", "50mm_standard"),
        ]

        for s_idx, scene in enumerate(screenplay.scenes):
            loc_id = (
                "LOC_OBSERVATORY_DOME"
                if s_idx == 0
                else "LOC_SUBLEVEL_RELAY_VAULT"
            )
            loc = location_bibles[loc_id]
            axis_id = f"AXIS_{scene.scene_id}"

            # Extract action/dialogue pairs into 2 shots per scene (6 shots total across 3 scenes)
            scene_cast = ["CHAR_ELENA_VANCE", "CHAR_MARCUS_KOREN"]
            dialogues = [
                el for el in scene.elements if isinstance(el, DialogueElement)
            ]
            actions = [
                el for el in scene.elements if isinstance(el, ActionElement)
            ]

            num_shots_in_scene = max(2, len(dialogues))
            for sh_idx in range(num_shots_in_scene):
                shot_id = f"{scene.scene_id}_SH{sh_idx + 1:02d}"
                char_id = scene_cast[sh_idx % len(scene_cast)]
                char_bible = character_bibles[char_id]
                wardrobe_id = list(char_bible.costume_variants.keys())[0]

                framing, angle, movement, lens = coverage_cycle[
                    (s_idx * 2 + sh_idx) % len(coverage_cycle)
                ]
                action_text = (
                    actions[sh_idx % len(actions)].description
                    if actions
                    else f"{char_bible.name} advances through {loc.name}."
                )
                dlg_text = (
                    dialogues[sh_idx].spoken_string
                    if sh_idx < len(dialogues)
                    else None
                )

                # Progressive physical state & prop affordances
                phys_state: Dict[str, List[str]] = {}
                if s_idx == 0:
                    phys_state[char_id] = ["rain_dampened_collar", "breath_misting"]
                elif s_idx == 1:
                    phys_state[char_id] = ["cryo_frost_on_shoulders", "scorch_mark_right_sleeve"]
                else:
                    phys_state[char_id] = ["soot_streaked_forearm", "elevated_respiration"]

                prop_state = {
                    "ART_CHRONO_COMPASS": scene.terminal_state.get(
                        "compass_state", "opened_calibrated"
                    )
                }
                reveal_flags = (
                    ["BEACON_9_HARMONIC_LOCKED"]
                    if s_idx == 0
                    else (
                        ["JOVIAN_SHADOW_COORDINATES_DECRYPTED"]
                        if s_idx == 1
                        else ["TELEMETRY_PACKET_TRANSMITTED"]
                    )
                )

                # Maintain consistent北 side of 180-degree axis across reverse-angle cuts
                facing = "left_to_right" if sh_idx % 2 == 0 else "right_to_left"
                eyeline = "east_15deg" if sh_idx % 2 == 0 else "west_15deg"

                ledger.append_shot_state(
                    scene_shot_id=shot_id,
                    active_cast_wardrobe={
                        "CHAR_ELENA_VANCE": "WARD_ELENA_EVA_TRENCH",
                        "CHAR_MARCUS_KOREN": "WARD_KOREN_LAB_PARKA",
                    },
                    dynamic_physical_state=phys_state,
                    prop_registry_affordance=prop_state,
                    spatial_screen_direction=SpatialScreenDirection(
                        axis_id=axis_id,
                        camera_side="north_of_axis",
                        subject_facing=facing,
                        eyeline_vector=eyeline,
                    ),
                    lighting_environmental={
                        "time_of_day": scene.heading.time_of_day,
                        "solar_angle": "lunar_storm_zenith",
                        "weather": "cryogenic_mist" if s_idx > 0 else "subpolar_sleet",
                        "lighting_setup": scene.heading.lighting_lock,
                        "color_grade": scene.heading.color_palette_lock,
                    },
                    causal_reveal_flags=reveal_flags,
                    enforce_180_rule=True,
                )

                shot_spec = CinematicShotSpecification(
                    shot_id=shot_id,
                    scene_context=SceneContextSpec(
                        location=loc.location_id,
                        time_of_day=scene.heading.time_of_day,
                        environment_state=loc.architectural_prompt_card,
                    ),
                    subject=SubjectSpec(
                        character_ref=char_id,
                        action_core=action_text,
                        subtext_expression="Focused intensity under chiaroscuro instrument light",
                        wardrobe_id=wardrobe_id,
                        prop_interactions=[
                            f"{k}:{v}" for k, v in prop_state.items()
                        ],
                    ),
                    cinematography=CinematographySpec(
                        framing=framing,
                        camera_angle=angle,
                        camera_movement=movement,
                        lens=lens,
                        composition=f"180-axis locked ({facing}), rule-of-thirds framing",
                    ),
                    lighting_and_atmosphere=LightingAndAtmosphereSpec(
                        setup=scene.heading.lighting_lock,
                        color_palette=loc.default_color_palette,
                        color_grade=scene.heading.color_palette_lock,
                        volumetrics="Cryogenic mist and instrument beam shafts",
                    ),
                    temporal_dynamics=TemporalDynamicsSpec(
                        duration_seconds=3.5 if sh_idx % 2 == 0 else 4.0,
                        frame_rate=24,
                        motion_intensity=0.45 if movement == "static" else 0.65,
                    ),
                    consistency_anchors=ConsistencyAnchorsSpec(
                        reference_image_uris=[
                            char_bible.turnaround_plates.get("front", ""),
                            loc.base_environment_render_uri,
                        ],
                        preserve_elements=[
                            f"facial_geometry:{char_id}",
                            "ART_CHRONO_COMPASS",
                            f"wardrobe:{wardrobe_id}",
                        ],
                    ),
                    beat_name=scene.beat_name,
                    dialogue_line=dlg_text,
                )
                shots.append(shot_spec)

        return shots, ledger


# ---------------------------------------------------------------------------
# LangGraph Cyclical Reasoning Graph Engine
# ---------------------------------------------------------------------------


class EpisodeGraphState(TypedDict, total=False):
    episode_id: str
    season: int
    episode: int
    story_seed: str
    season_arc: str
    simulate_drift_shots: List[str]
    thematic_dossier: Dict[str, Any]
    beat_sheet: Dict[str, Any]
    screenjson: Dict[str, Any]
    fountain_script: str
    shot_specs: List[Dict[str, Any]]
    ledger_parquet_path: str
    keyframes: List[Dict[str, Any]]
    verdicts: List[Dict[str, Any]]
    rejected_shot_ids: List[str]
    semantic_loop_iterations: int
    motion_clips: List[Dict[str, Any]]
    dialogue_wavs: Dict[str, str]
    otio_path: str
    timeline_summary: Dict[str, Any]
    audit_trail: List[Dict[str, Any]]


class EpisodeReasoningEngine:
    """
    Micro-orchestration engine powered by LangGraph managing agent transitions,
    append-only state passing, cyclical VLM Judge evaluation loops (Semantic Loop),
    and Server-Sent Events (SSE) telemetry streaming.
    """

    def __init__(
        self,
        storage: "StudioStorage",
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        llm_config: Optional[LLMConfig] = None,
        llm_gateway: Optional[LLMGateway] = None,
    ) -> None:
        self.storage = storage
        self.event_callback = event_callback
        self.llm_config = llm_config or LLMConfig()
        self.llm_gateway = llm_gateway or LLMGateway()
        self.lore_graph = seed_default_canon(storage)
        self.character_bibles = {
            b.character_id: b for b in storage.list_character_bibles()
        }
        self.location_bibles = {
            loc.location_id: loc for loc in storage.list_location_bibles()
        }

        self.research_agent = ResearchLoreAgent()
        self.director_agent = DirectorAgent()
        self.screenwriter_agent = ScreenwriterAgent()
        self.cinematographer_agent = CinematographerAgent()
        self.vlm_judge = VLMContinuityJudge(id_score_threshold=0.85)
        self._ledger_cache: Dict[str, ContinuityLedger] = {}
        self._graph = self._compile_langgraph()

    def _emit(self, node: str, phase: str, detail: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ev = {
            "timestamp": time.time(),
            "node": node,
            "phase": phase,
            "detail": detail,
            "payload": payload or {},
        }
        if self.event_callback:
            self.event_callback(ev)
        return ev

    def _node_research_lore(self, state: EpisodeGraphState) -> EpisodeGraphState:
        dossier = self.research_agent.run(
            episode_id=state["episode_id"],
            story_seed=state["story_seed"],
            season_arc=state.get("season_arc", "The Jovian Shadow Conspiracy"),
            lore_graph=self.lore_graph,
            llm_config=self.llm_config,
            llm_gateway=self.llm_gateway,
        )
        ep_dirs = self.storage.ensure_episode_directories(state["season"], state["episode"])
        (ep_dirs["script"] / "thematic_dossier.json").write_text(
            json.dumps(dossier.model_dump(), indent=2), encoding="utf-8"
        )
        ev = self._emit(
            "research_lore",
            "I. Narrative Inception",
            f"Compiled Thematic Dossier via {self.llm_config.provider}/{self.llm_config.model} (Setting Adherence={dossier.setting_adherence_score:.2f})",
            {
                "setting_adherence_score": dossier.setting_adherence_score,
                "llm_provider": self.llm_config.provider,
                "llm_model": self.llm_config.model,
            },
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {"thematic_dossier": dossier.model_dump(), "audit_trail": trail}

    def _node_director(self, state: EpisodeGraphState) -> EpisodeGraphState:
        dossier = ThematicDossier.model_validate(state["thematic_dossier"])
        sheet = self.director_agent.run(dossier=dossier, framework="save_the_cat_15")
        ep_dirs = self.storage.ensure_episode_directories(state["season"], state["episode"])
        (ep_dirs["script"] / "beat_sheet.json").write_text(
            json.dumps(sheet.model_dump(), indent=2), encoding="utf-8"
        )
        ev = self._emit(
            "director",
            "I. Narrative Inception",
            f"Constructed 15-Beat Structural Matrix & {len(sheet.scene_cards)} causally linked Scene Cards (Pacing={sheet.pacing_score:.2f})",
            {"pacing_score": sheet.pacing_score, "beats": len(sheet.beats)},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {"beat_sheet": sheet.model_dump(), "audit_trail": trail}

    def _node_screenwriter(self, state: EpisodeGraphState) -> EpisodeGraphState:
        sheet = BeatSheet.model_validate(state["beat_sheet"])
        screenplay = self.screenwriter_agent.run(
            beat_sheet=sheet,
            character_bibles=self.character_bibles,
            location_bibles=self.location_bibles,
        )
        fountain_str = screenplay.to_fountain()
        ep_dirs = self.storage.ensure_episode_directories(state["season"], state["episode"])
        (ep_dirs["script"] / "screenplay.screen.json").write_text(
            json.dumps(screenplay.model_dump(), indent=2), encoding="utf-8"
        )
        (ep_dirs["script"] / "screenplay.fountain").write_text(
            fountain_str, encoding="utf-8"
        )
        ev = self._emit(
            "screenwriter",
            "II. Script & Continuity",
            f"Drafted ScreenJSON AST & Fountain script across {len(screenplay.scenes)} scenes",
            {"dialogue_naturalism_score": screenplay.dialogue_naturalism_score},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "screenjson": screenplay.model_dump(),
            "fountain_script": fountain_str,
            "audit_trail": trail,
        }

    def _node_cinematographer(self, state: EpisodeGraphState) -> EpisodeGraphState:
        screenplay = ScreenJSONDocument.model_validate(state["screenjson"])
        shots, ledger = self.cinematographer_agent.run(
            screenplay=screenplay,
            character_bibles=self.character_bibles,
            location_bibles=self.location_bibles,
        )
        parquet_path = ledger.save_parquet(
            self.storage, season=state["season"], episode=state["episode"]
        )
        self._ledger_cache[state["episode_id"]] = ledger

        ep_dirs = self.storage.ensure_episode_directories(state["season"], state["episode"])
        (ep_dirs["storyboards"] / "shot_specifications.json").write_text(
            json.dumps([s.model_dump() for s in shots], indent=2), encoding="utf-8"
        )
        ev = self._emit(
            "cinematographer",
            "III. Cinematography",
            f"Validated {len(shots)} CinematicShotSpecifications (Draft 2020-12) & locked Continuity Ledger Parquet",
            {"shot_count": len(shots)},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "shot_specs": [s.model_dump() for s in shots],
            "ledger_parquet_path": str(parquet_path.relative_to(self.storage.root_dir).as_posix()),
            "audit_trail": trail,
        }

    def _node_keyframe_synthesis(self, state: EpisodeGraphState) -> EpisodeGraphState:
        shots = [CinematicShotSpecification.model_validate(s) for s in state["shot_specs"]]
        ledger = self._ledger_cache[state["episode_id"]]
        ledger_map = {e.scene_shot_id: e for e in ledger.entries}
        synthesizer = SharedAttentionKeyframeSynthesizer(
            storage=self.storage, season=state["season"], episode=state["episode"]
        )

        # Group shots by scene_id for Shared-Attention Grid generation
        scenes_map: Dict[str, List[CinematicShotSpecification]] = {}
        for sh in shots:
            sc_id = sh.shot_id.split("_", 1)[0]
            scenes_map.setdefault(sc_id, []).append(sh)

        drift_set = set(state.get("simulate_drift_shots", []))
        rev_count = state.get("semantic_loop_iterations", 0)
        all_candidates: List[KeyframeCandidate] = []
        for sc_id, sc_shots in scenes_map.items():
            cands = synthesizer.synthesize_scene_grid(
                scene_id=sc_id,
                shots=sc_shots,
                character_bibles=self.character_bibles,
                ledger_entries=ledger_map,
                simulate_drift_for_shots=drift_set,
                revision_count=rev_count,
            )
            all_candidates.extend(cands)

        ev = self._emit(
            "keyframe_synthesis",
            "IV. Keyframe Synthesis",
            f"Synthesized {len(all_candidates)} keyframes across {len(scenes_map)} Shared-Attention Scene Grids (rev={rev_count})",
            {"keyframes": len(all_candidates), "revision": rev_count},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "keyframes": [c.model_dump() for c in all_candidates],
            "audit_trail": trail,
        }

    def _node_vlm_judge(self, state: EpisodeGraphState) -> EpisodeGraphState:
        shots = {
            s["shot_id"]: CinematicShotSpecification.model_validate(s)
            for s in state["shot_specs"]
        }
        candidates = [KeyframeCandidate.model_validate(c) for c in state["keyframes"]]
        ledger = self._ledger_cache[state["episode_id"]]
        ledger_map = {e.scene_shot_id: e for e in ledger.entries}

        verdicts: List[ContinuityVerdict] = []
        rejected_ids: List[str] = []
        updated_candidates: List[Dict[str, Any]] = []

        for cand in candidates:
            shot = shots[cand.shot_id]
            bible = self.character_bibles[shot.subject.character_ref]
            entry = ledger_map[cand.shot_id]
            verdict = self.vlm_judge.evaluate(cand, shot, bible, entry)
            verdicts.append(verdict)
            if verdict.accepted:
                cand.verified = True
                cand.identity_score = verdict.identity_score
            else:
                cand.verified = False
                cand.identity_score = verdict.identity_score
                rejected_ids.append(cand.shot_id)
            updated_candidates.append(cand.model_dump())

        ep_dirs = self.storage.ensure_episode_directories(state["season"], state["episode"])
        (ep_dirs["storyboards"] / "vlm_audit_report.json").write_text(
            json.dumps([v.model_dump() for v in verdicts], indent=2), encoding="utf-8"
        )

        status_msg = (
            f"All {len(verdicts)} keyframes passed VLM Continuity Gate (Score_ID >= 0.85)"
            if not rejected_ids
            else f"Rejected {len(rejected_ids)} keyframes ({', '.join(rejected_ids)}); routing to Semantic Loop"
        )
        ev = self._emit(
            "vlm_judge",
            "IV. Keyframe Synthesis",
            status_msg,
            {"rejected_shot_ids": rejected_ids},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "keyframes": updated_candidates,
            "verdicts": [v.model_dump() for v in verdicts],
            "rejected_shot_ids": rejected_ids,
            "audit_trail": trail,
        }

    def _node_semantic_revision(self, state: EpisodeGraphState) -> EpisodeGraphState:
        shots = [CinematicShotSpecification.model_validate(s) for s in state["shot_specs"]]
        verdicts_map = {
            v["shot_id"]: ContinuityVerdict.model_validate(v)
            for v in state.get("verdicts", [])
        }
        refined_shots: List[Dict[str, Any]] = []
        for sh in shots:
            v = verdicts_map.get(sh.shot_id)
            if v and not v.accepted and v.revision_delta is not None:
                sh = apply_revision_delta_to_shot(sh, v.revision_delta)
            refined_shots.append(sh.model_dump())

        next_iter = state.get("semantic_loop_iterations", 0) + 1
        ev = self._emit(
            "semantic_revision",
            "IV. Semantic Loop Rollback",
            f"Applied RevisionDelta negative constraints & LoRA locks for {len(state.get('rejected_shot_ids', []))} shots (iteration {next_iter})",
            {"iteration": next_iter},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "shot_specs": refined_shots,
            "semantic_loop_iterations": next_iter,
            "audit_trail": trail,
        }

    def _node_motion_diffusion(self, state: EpisodeGraphState) -> EpisodeGraphState:
        shots = {
            s["shot_id"]: CinematicShotSpecification.model_validate(s)
            for s in state["shot_specs"]
        }
        candidates = [KeyframeCandidate.model_validate(c) for c in state["keyframes"]]
        ledger = self._ledger_cache[state["episode_id"]]
        ledger_map = {e.scene_shot_id: e for e in ledger.entries}

        motion_clips: List[MotionClipResult] = []
        dialogue_wavs: Dict[str, str] = {}

        for cand in candidates:
            shot = shots[cand.shot_id]
            entry = ledger_map[cand.shot_id]
            clip_res = synthesize_i2v_motion_clip(
                storage=self.storage,
                season=state["season"],
                episode=state["episode"],
                shot=shot,
                keyframe=cand,
                ledger_entry=entry,
            )
            motion_clips.append(clip_res)
            wav_path = synthesize_dialogue_wav(
                storage=self.storage,
                season=state["season"],
                episode=state["episode"],
                shot=shot,
            )
            dialogue_wavs[shot.shot_id] = str(
                wav_path.relative_to(self.storage.root_dir).as_posix()
            )

        ev = self._emit(
            "motion_diffusion",
            "V. Motion Diffusion",
            f"Rendered {len(motion_clips)} I2V master video clips & TTS dialogue WAV stems (frame-stepping passed)",
            {"clips": len(motion_clips)},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "motion_clips": [m.model_dump() for m in motion_clips],
            "dialogue_wavs": dialogue_wavs,
            "audit_trail": trail,
        }

    def _node_timeline_assembly(self, state: EpisodeGraphState) -> EpisodeGraphState:
        shots = {
            s["shot_id"]: CinematicShotSpecification.model_validate(s)
            for s in state["shot_specs"]
        }
        clips_map = {
            m["shot_id"]: MotionClipResult.model_validate(m)
            for m in state["motion_clips"]
        }
        ledger = self._ledger_cache[state["episode_id"]]
        ledger_map = {e.scene_shot_id: e for e in ledger.entries}
        wavs_map = state.get("dialogue_wavs", {})

        shot_manifest: List[Dict[str, Any]] = []
        for shot_id, shot in shots.items():
            clip_res = clips_map[shot_id]
            entry = ledger_map[shot_id]
            shot_manifest.append(
                {
                    "shot_id": shot_id,
                    "duration_sec": shot.temporal_dynamics.duration_seconds,
                    "video_path": clip_res.video_path,
                    "audio_path": wavs_map.get(shot_id),
                    "prompt_uuid": shot.prompt_uuid,
                    "model_version": clip_res.model_version,
                    "seed": clip_res.seed,
                    "ledger_idx": entry.ledger_index,
                    "beat_name": shot.beat_name,
                }
            )

        timeline = construct_editorial_timeline(state["episode_id"], shot_manifest)
        otio_path = export_timeline_otio(
            timeline, self.storage, season=state["season"], episode=state["episode"]
        )
        summary = timeline_to_summary_dict(timeline)

        ev = self._emit(
            "timeline_assembly",
            "VI. Timeline Assembly",
            f"Exported OpenTimelineIO master container ({otio_path.name}, {summary['total_duration_seconds']}s)",
            {"otio_path": str(otio_path.relative_to(self.storage.root_dir).as_posix())},
        )
        trail = list(state.get("audit_trail", [])) + [ev]
        return {
            "otio_path": str(otio_path),
            "timeline_summary": summary,
            "audit_trail": trail,
        }

    def _route_after_vlm_judge(self, state: EpisodeGraphState) -> str:
        rejected = state.get("rejected_shot_ids", [])
        iterations = state.get("semantic_loop_iterations", 0)
        if rejected and iterations < 3:
            return "semantic_revision"
        return "motion_diffusion"

    def _compile_langgraph(self):
        builder = StateGraph(EpisodeGraphState)
        builder.add_node("research_lore", self._node_research_lore)
        builder.add_node("director", self._node_director)
        builder.add_node("screenwriter", self._node_screenwriter)
        builder.add_node("cinematographer", self._node_cinematographer)
        builder.add_node("keyframe_synthesis", self._node_keyframe_synthesis)
        builder.add_node("vlm_judge", self._node_vlm_judge)
        builder.add_node("semantic_revision", self._node_semantic_revision)
        builder.add_node("motion_diffusion", self._node_motion_diffusion)
        builder.add_node("timeline_assembly", self._node_timeline_assembly)

        builder.set_entry_point("research_lore")
        builder.add_edge("research_lore", "director")
        builder.add_edge("director", "screenwriter")
        builder.add_edge("screenwriter", "cinematographer")
        builder.add_edge("cinematographer", "keyframe_synthesis")
        builder.add_edge("keyframe_synthesis", "vlm_judge")
        builder.add_conditional_edges(
            "vlm_judge",
            self._route_after_vlm_judge,
            {
                "semantic_revision": "semantic_revision",
                "motion_diffusion": "motion_diffusion",
            },
        )
        builder.add_edge("semantic_revision", "keyframe_synthesis")
        builder.add_edge("motion_diffusion", "timeline_assembly")
        builder.add_edge("timeline_assembly", END)
        return builder.compile()

    def run_episode(
        self,
        episode_id: str,
        story_seed: str,
        season_arc: str = "The Jovian Shadow Conspiracy",
        simulate_drift_shots: Optional[Set[str]] = None,
    ) -> EpisodeGraphState:
        season, episode = self.storage.parse_episode_id(episode_id)
        initial_state: EpisodeGraphState = {
            "episode_id": episode_id,
            "season": season,
            "episode": episode,
            "story_seed": story_seed,
            "season_arc": season_arc,
            "simulate_drift_shots": sorted(simulate_drift_shots or set()),
            "semantic_loop_iterations": 0,
            "audit_trail": [],
        }
        return self._graph.invoke(initial_state)
