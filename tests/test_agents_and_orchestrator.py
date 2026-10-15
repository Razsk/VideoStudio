from pathlib import Path

from videostudio.agents import EpisodeReasoningEngine
from videostudio.orchestrator import DurableMacroOrchestrator, RetryPolicyConfig
from videostudio.storage import StudioStorage


def test_langgraph_reasoning_engine_executes_all_phases_with_semantic_loop(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    events = []

    engine = EpisodeReasoningEngine(
        storage=storage,
        event_callback=lambda ev: events.append(ev),
    )

    # Simulate drift on SC01_SH01 so the VLM Judge Gate triggers the cyclical Semantic Loop
    final_state = engine.run_episode(
        episode_id="S01E01",
        story_seed="An encrypted signal from decommissioned Beacon 9 forces Elena Vance and Marcus Koren into the cryogenic relay vault.",
        season_arc="The Jovian Shadow Conspiracy",
        simulate_drift_shots={"SC01_SH01"},
    )

    assert final_state["thematic_dossier"]["setting_adherence_score"] >= 0.85
    assert len(final_state["beat_sheet"]["beats"]) == 15
    assert len(final_state["screenjson"]["scenes"]) >= 2
    assert len(final_state["shot_specs"]) >= 4
    assert final_state["semantic_loop_iterations"] >= 1
    assert all(kf["verified"] for kf in final_state["keyframes"])
    assert all(kf["identity_score"] >= 0.85 for kf in final_state["keyframes"])
    assert Path(final_state["otio_path"]).exists()

    # Check SSE events captured the cyclical Semantic Loop transition
    node_names = [e["node"] for e in events]
    assert "research_lore" in node_names
    assert "director" in node_names
    assert "screenwriter" in node_names
    assert "cinematographer" in node_names
    assert "keyframe_synthesis" in node_names
    assert "vlm_judge" in node_names
    assert "semantic_revision" in node_names
    assert "motion_diffusion" in node_names
    assert "timeline_assembly" in node_names


def test_durable_macro_orchestrator_checkpoints_retries_and_human_gates(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    orchestrator = DurableMacroOrchestrator(
        storage=storage,
        retry_policy=RetryPolicyConfig(max_attempts=3, initial_backoff_seconds=0.01),
    )

    # 1. Run with Human Gate pause at Phase I (narrative_arc_signoff)
    paused_run = orchestrator.execute_episode_workflow(
        episode_id="S01E01",
        story_seed="Strange telemetry echoes across the Helios Observatory dome.",
        pause_at_human_gate="phase_1_narrative_arc",
    )
    assert paused_run.status == "WAITING_FOR_HUMAN_GATE"
    assert paused_run.pending_gate == "phase_1_narrative_arc"

    # 2. Approve the Human Gate and resume from checkpoint without re-running completed activities
    completed_run = orchestrator.approve_human_gate_and_resume(
        workflow_id=paused_run.workflow_id,
        gate_name="phase_1_narrative_arc",
        reviewer_notes="Arc approved: strong Midpoint reversal in the relay vault.",
    )
    assert completed_run.status == "COMPLETED"
    assert completed_run.otio_timeline_path is not None
    assert (tmp_path / completed_run.otio_timeline_path).exists()

    # Verify durable workflow event history log
    history = orchestrator.load_workflow_history(season=1, episode=1)
    event_types = [h["event_type"] for h in history]
    assert "WORKFLOW_STARTED" in event_types
    assert "HUMAN_GATE_PAUSED" in event_types
    assert "HUMAN_GATE_APPROVED" in event_types
    assert "WORKFLOW_COMPLETED" in event_types
