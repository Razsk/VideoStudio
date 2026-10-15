from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from videostudio.agents import EpisodeGraphState, EpisodeReasoningEngine
from videostudio.llm import LLMConfig, LLMGateway, SecureCredentialStore, redact_secrets

if TYPE_CHECKING:
    from videostudio.storage import StudioStorage


class RetryPolicyConfig(BaseModel):
    max_attempts: int = 4
    initial_backoff_seconds: float = 0.05
    backoff_coefficient: float = 2.0


class WorkflowRunState(BaseModel):
    workflow_id: str
    episode_id: str
    season: int
    episode: int
    story_seed: str
    season_arc: str
    status: Literal[
        "RUNNING",
        "WAITING_FOR_HUMAN_GATE",
        "COMPLETED",
        "FAILED",
    ]
    completed_phases: List[str] = Field(default_factory=list)
    pending_gate: Optional[str] = None
    human_approvals: Dict[str, str] = Field(default_factory=dict)
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    graph_state: Dict[str, Any] = Field(default_factory=dict)
    otio_timeline_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Temporal.io Native Workflow & Activity Definitions (Macro-Orchestrator)
# ---------------------------------------------------------------------------


@activity.defn(name="execute_langgraph_episode_activity")
async def execute_langgraph_episode_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    from videostudio.storage import StudioStorage

    storage = StudioStorage(root_dir=params.get("root_dir", "."))
    llm_cfg = LLMConfig.model_validate(params.get("llm_config", {})) if params.get("llm_config") else LLMConfig()
    engine = EpisodeReasoningEngine(storage=storage, llm_config=llm_cfg)
    state = engine.run_episode(
        episode_id=params["episode_id"],
        story_seed=params["story_seed"],
        season_arc=params.get("season_arc", "The Jovian Shadow Conspiracy"),
        simulate_drift_shots=set(params.get("simulate_drift_shots", [])),
    )
    return dict(state)


@workflow.defn(name="EpisodicProductionWorkflow")
class EpisodicProductionWorkflow:
    """
    Temporal Macro-Orchestrator governing durable execution histories,
    GPU task queues, and exponential backoff retries.
    """

    @workflow.run
    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await workflow.execute_activity(
            execute_langgraph_episode_activity,
            params,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=4,
            ),
        )


# ---------------------------------------------------------------------------
# Durable Local & Checkpointed Macro-Orchestrator Engine
# ---------------------------------------------------------------------------


class DurableMacroOrchestrator:
    """
    Macro-Orchestrator managing durable append-only workflow event histories,
    checkpointed phase boundaries, exponential backoff retries, and Human Gate pauses.
    """

    PHASES = [
        ("phase_1_narrative_inception", [" _node_research_lore", "_node_director"]),
        ("phase_2_script_and_continuity", ["_node_screenwriter"]),
        ("phase_3_cinematography", ["_node_cinematographer"]),
        ("phase_4_keyframe_and_vlm_gate", ["_node_keyframe_synthesis", "_node_vlm_judge"]),
        ("phase_5_motion_diffusion", ["_node_motion_diffusion"]),
        ("phase_6_timeline_assembly", ["_node_timeline_assembly"]),
    ]

    def __init__(
        self,
        storage: "StudioStorage",
        retry_policy: Optional[RetryPolicyConfig] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        credential_store: Optional[SecureCredentialStore] = None,
    ) -> None:
        self.storage = storage
        self.retry_policy = retry_policy or RetryPolicyConfig()
        self.event_callback = event_callback
        self.credential_store = credential_store or SecureCredentialStore()
        self._runs: Dict[str, WorkflowRunState] = {}

    def _history_file(self, season: int, episode: int) -> Path:
        ep_dirs = self.storage.ensure_episode_directories(season, episode)
        return ep_dirs["editorial"] / "workflow_history.jsonl"

    def _checkpoint_file(self, season: int, episode: int) -> Path:
        ep_dirs = self.storage.ensure_episode_directories(season, episode)
        return ep_dirs["editorial"] / "workflow_checkpoint.json"

    def _append_history_event(
        self,
        season: int,
        episode: int,
        workflow_id: str,
        event_type: str,
        details: Dict[str, Any],
    ) -> None:
        record = {
            "timestamp": time.time(),
            "workflow_id": workflow_id,
            "event_type": event_type,
            "details": details,
        }
        path = self._history_file(season, episode)
        with path.open("a", encoding="utf-8") as f:
            f.write(redact_secrets(json.dumps(record)) + "\n")

    def load_workflow_history(self, season: int, episode: int) -> List[Dict[str, Any]]:
        path = self._history_file(season, episode)
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _save_checkpoint(self, run_state: WorkflowRunState) -> None:
        self._runs[run_state.workflow_id] = run_state
        ckpt_path = self._checkpoint_file(run_state.season, run_state.episode)
        ckpt_path.write_text(
            redact_secrets(json.dumps(run_state.model_dump(), indent=2)),
            encoding="utf-8",
        )

    def get_run(self, workflow_id: str) -> WorkflowRunState:
        if workflow_id in self._runs:
            return self._runs[workflow_id]
        for ckpt in self.storage.root_dir.glob("season_*/episode_*/editorial/workflow_checkpoint.json"):
            data = json.loads(ckpt.read_text(encoding="utf-8"))
            if data.get("workflow_id") == workflow_id:
                run = WorkflowRunState.model_validate(data)
                self._runs[workflow_id] = run
                return run
        raise KeyError(f"Workflow {workflow_id} not found")

    def _execute_with_retry(
        self,
        season: int,
        episode: int,
        workflow_id: str,
        activity_name: str,
        fn: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        attempt = 0
        backoff = self.retry_policy.initial_backoff_seconds
        while True:
            attempt += 1
            try:
                self._append_history_event(
                    season,
                    episode,
                    workflow_id,
                    "ACTIVITY_STARTED",
                    {"activity": activity_name, "attempt": attempt},
                )
                result = fn()
                self._append_history_event(
                    season,
                    episode,
                    workflow_id,
                    "ACTIVITY_COMPLETED",
                    {"activity": activity_name, "attempt": attempt},
                )
                return result
            except Exception as exc:
                self._append_history_event(
                    season,
                    episode,
                    workflow_id,
                    "ACTIVITY_FAILED",
                    {
                        "activity": activity_name,
                        "attempt": attempt,
                        "error": redact_secrets(str(exc)),
                    },
                )
                if attempt >= self.retry_policy.max_attempts:
                    raise
                time.sleep(backoff)
                backoff *= self.retry_policy.backoff_coefficient

    def execute_episode_workflow(
        self,
        episode_id: str,
        story_seed: str,
        season_arc: str = "The Jovian Shadow Conspiracy",
        simulate_drift_shots: Optional[Set[str]] = None,
        pause_at_human_gate: Optional[
            Literal[
                "phase_1_narrative_arc",
                "phase_2_dialogue_tone",
                "phase_6_final_playback",
            ]
        ] = None,
        workflow_id: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
    ) -> WorkflowRunState:
        season, episode = self.storage.parse_episode_id(episode_id)
        wf_id = workflow_id or f"wf-{episode_id.lower()}-{uuid.uuid4().hex[:8]}"
        resolved_llm_config = llm_config or LLMConfig()

        if wf_id in self._runs:
            run_state = self._runs[wf_id]
            run_state.status = "RUNNING"
            run_state.pending_gate = None
            resolved_llm_config = run_state.llm_config
        else:
            initial_graph_state: EpisodeGraphState = {
                "episode_id": episode_id,
                "season": season,
                "episode": episode,
                "story_seed": story_seed,
                "season_arc": season_arc,
                "simulate_drift_shots": sorted(simulate_drift_shots or set()),
                "semantic_loop_iterations": 0,
                "audit_trail": [],
            }
            run_state = WorkflowRunState(
                workflow_id=wf_id,
                episode_id=episode_id,
                season=season,
                episode=episode,
                story_seed=story_seed,
                season_arc=season_arc,
                status="RUNNING",
                llm_config=resolved_llm_config,
                graph_state=dict(initial_graph_state),
            )
            self._append_history_event(
                season,
                episode,
                wf_id,
                "WORKFLOW_STARTED",
                {
                    "episode_id": episode_id,
                    "story_seed": story_seed,
                    "llm_provider": resolved_llm_config.provider,
                    "llm_model": resolved_llm_config.model,
                },
            )

        gateway = LLMGateway(credential_store=self.credential_store)
        engine = EpisodeReasoningEngine(
            storage=self.storage,
            event_callback=self.event_callback,
            llm_config=resolved_llm_config,
            llm_gateway=gateway,
        )

        # Rehydrate ledger cache if resuming after Phase III
        if (
            "phase_3_cinematography" in run_state.completed_phases
            and run_state.graph_state.get("ledger_parquet_path")
        ):
            from videostudio.continuity import ContinuityLedger

            pq_path = self.storage.root_dir / run_state.graph_state["ledger_parquet_path"]
            if pq_path.exists():
                engine._ledger_cache[episode_id] = ContinuityLedger.load_parquet(
                    pq_path, episode_id=episode_id
                )

        # Phase I: Narrative Inception (Research + Director)
        if "phase_1_narrative_inception" not in run_state.completed_phases:
            res_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "research_lore_activity",
                lambda: engine._node_research_lore(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(res_update)
            dir_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "director_activity",
                lambda: engine._node_director(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(dir_update)
            run_state.completed_phases.append("phase_1_narrative_inception")
            self._save_checkpoint(run_state)

            if (
                pause_at_human_gate == "phase_1_narrative_arc"
                and "phase_1_narrative_arc" not in run_state.human_approvals
            ):
                run_state.status = "WAITING_FOR_HUMAN_GATE"
                run_state.pending_gate = "phase_1_narrative_arc"
                self._append_history_event(
                    season,
                    episode,
                    wf_id,
                    "HUMAN_GATE_PAUSED",
                    {"gate": "phase_1_narrative_arc"},
                )
                self._save_checkpoint(run_state)
                return run_state

        # Phase II: Script & Continuity (Screenwriter)
        if "phase_2_script_and_continuity" not in run_state.completed_phases:
            scr_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "screenwriter_activity",
                lambda: engine._node_screenwriter(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(scr_update)
            run_state.completed_phases.append("phase_2_script_and_continuity")
            self._save_checkpoint(run_state)

            if (
                pause_at_human_gate == "phase_2_dialogue_tone"
                and "phase_2_dialogue_tone" not in run_state.human_approvals
            ):
                run_state.status = "WAITING_FOR_HUMAN_GATE"
                run_state.pending_gate = "phase_2_dialogue_tone"
                self._append_history_event(
                    season,
                    episode,
                    wf_id,
                    "HUMAN_GATE_PAUSED",
                    {"gate": "phase_2_dialogue_tone"},
                )
                self._save_checkpoint(run_state)
                return run_state

        # Phase III: Cinematography
        if "phase_3_cinematography" not in run_state.completed_phases:
            cin_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "cinematographer_activity",
                lambda: engine._node_cinematographer(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(cin_update)
            run_state.completed_phases.append("phase_3_cinematography")
            self._save_checkpoint(run_state)

        # Phase IV: Keyframe Synthesis & Cyclical VLM Judge Gate (Semantic Loop)
        if "phase_4_keyframe_and_vlm_gate" not in run_state.completed_phases:
            while True:
                kf_update = self._execute_with_retry(
                    season,
                    episode,
                    wf_id,
                    "keyframe_synthesis_activity",
                    lambda: engine._node_keyframe_synthesis(run_state.graph_state),  # type: ignore[arg-type]
                )
                run_state.graph_state.update(kf_update)

                vlm_update = self._execute_with_retry(
                    season,
                    episode,
                    wf_id,
                    "vlm_judge_activity",
                    lambda: engine._node_vlm_judge(run_state.graph_state),  # type: ignore[arg-type]
                )
                run_state.graph_state.update(vlm_update)

                next_step = engine._route_after_vlm_judge(run_state.graph_state)  # type: ignore[arg-type]
                if next_step == "semantic_revision":
                    rev_update = self._execute_with_retry(
                        season,
                        episode,
                        wf_id,
                        "semantic_revision_activity",
                        lambda: engine._node_semantic_revision(run_state.graph_state),  # type: ignore[arg-type]
                    )
                    run_state.graph_state.update(rev_update)
                else:
                    break

            run_state.completed_phases.append("phase_4_keyframe_and_vlm_gate")
            self._save_checkpoint(run_state)

        # Phase V: I2V Motion Diffusion & TTS Audio
        if "phase_5_motion_diffusion" not in run_state.completed_phases:
            mot_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "motion_diffusion_activity",
                lambda: engine._node_motion_diffusion(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(mot_update)
            run_state.completed_phases.append("phase_5_motion_diffusion")
            self._save_checkpoint(run_state)

        # Phase VI: OpenTimelineIO Assembly
        if "phase_6_timeline_assembly" not in run_state.completed_phases:
            otio_update = self._execute_with_retry(
                season,
                episode,
                wf_id,
                "timeline_assembly_activity",
                lambda: engine._node_timeline_assembly(run_state.graph_state),  # type: ignore[arg-type]
            )
            run_state.graph_state.update(otio_update)
            run_state.completed_phases.append("phase_6_timeline_assembly")
            otio_abs = Path(run_state.graph_state["otio_path"])
            run_state.otio_timeline_path = str(
                otio_abs.relative_to(self.storage.root_dir).as_posix()
            )

        run_state.status = "COMPLETED"
        self._append_history_event(
            season,
            episode,
            wf_id,
            "WORKFLOW_COMPLETED",
            {"otio_timeline_path": run_state.otio_timeline_path},
        )
        self._save_checkpoint(run_state)
        return run_state

    def approve_human_gate_and_resume(
        self,
        workflow_id: str,
        gate_name: str,
        reviewer_notes: str = "Approved",
    ) -> WorkflowRunState:
        run_state = self.get_run(workflow_id)
        run_state.human_approvals[gate_name] = reviewer_notes
        self._append_history_event(
            run_state.season,
            run_state.episode,
            workflow_id,
            "HUMAN_GATE_APPROVED",
            {"gate": gate_name, "reviewer_notes": reviewer_notes},
        )
        self._save_checkpoint(run_state)
        return self.execute_episode_workflow(
            episode_id=run_state.episode_id,
            story_seed=run_state.story_seed,
            season_arc=run_state.season_arc,
            workflow_id=workflow_id,
        )
