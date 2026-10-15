from pathlib import Path

from fastapi.testclient import TestClient

from videostudio.cli import run_cli
from videostudio.server import create_app


def test_fastapi_server_endpoints_human_gate_sse_and_mutation(tmp_path: Path):
    app = create_app(root_dir=tmp_path)
    client = TestClient(app)

    # 1. Dashboard UI loads
    resp_ui = client.get("/")
    assert resp_ui.status_code == 200
    assert "VideoStudio" in resp_ui.text
    assert "OpenTimelineIO" in resp_ui.text

    # 2. Canon & GraphRAG query
    resp_canon = client.get("/api/canon")
    assert resp_canon.status_code == 200
    canon_data = resp_canon.json()
    assert len(canon_data["characters"]) >= 2
    assert len(canon_data["locations"]) >= 2
    assert "MERGE" in canon_data["neo4j_cypher"]

    resp_causal = client.post(
        "/api/lore/constraints",
        json={"character_id": "CHAR_ELENA_VANCE", "step": 2, "query": "observatory brass"},
    )
    assert resp_causal.status_code == 200
    assert "SECRET_GHOST_TELEMETRY" in resp_causal.json()["constraints"]["known_secrets"]

    # 3. Start workflow with Human Gate pause at Phase I
    resp_run = client.post(
        "/api/workflows/run",
        json={
            "episode_id": "S01E01",
            "story_seed": "Beacon 9 transmits an encrypted harmonic from the Jovian shadow.",
            "season_arc": "The Jovian Shadow Conspiracy",
            "simulate_drift_shots": ["SC01_SH01"],
            "pause_at_human_gate": "phase_1_narrative_arc",
        },
    )
    assert resp_run.status_code == 200
    run_data = resp_run.json()
    assert run_data["status"] == "WAITING_FOR_HUMAN_GATE"
    wf_id = run_data["workflow_id"]

    # 4. Approve Human Gate and resume to completion
    resp_approve = client.post(
        f"/api/workflows/{wf_id}/approve",
        json={
            "gate_name": "phase_1_narrative_arc",
            "reviewer_notes": "Approved 15-beat Save the Cat structure.",
        },
    )
    assert resp_approve.status_code == 200
    completed_data = resp_approve.json()
    assert completed_data["status"] == "COMPLETED"
    assert completed_data["graph_state"]["semantic_loop_iterations"] >= 1

    # 5. Fetch episodic artifacts & mutate upstream continuity ledger
    resp_art = client.get("/api/episodes/S01E01/artifacts")
    assert resp_art.status_code == 200
    art = resp_art.json()
    assert len(art["ledger_entries"]) >= 4
    assert art["timeline_summary"]["total_clips"] >= 4

    resp_mut = client.post(
        "/api/continuity/mutate",
        json={
            "episode_id": "S01E01",
            "scene_shot_id": "SC01_SH01",
            "added_physical_state": {"CHAR_ELENA_VANCE": ["frostbitten_left_cheek"]},
            "updated_props": {"ART_CHRONO_COMPASS": "lens_cracked"},
            "added_reveal_flags": ["EMERGENCY_CONTAINMENT_ACTIVE"],
            "reconcile": True,
        },
    )
    assert resp_mut.status_code == 200
    mut_data = resp_mut.json()
    assert len(mut_data["invalidated_shots"]) >= 3
    assert len(mut_data["reconciled_shots"]) >= 3
    last_entry = mut_data["entries"][-1]
    assert "frostbitten_left_cheek" in last_entry["dynamic_physical_state"]["CHAR_ELENA_VANCE"]


def test_cli_produce_episode_creates_full_artifact_hierarchy(tmp_path: Path):
    exit_code = run_cli(
        [
            "produce",
            "--root-dir",
            str(tmp_path),
            "--episode-id",
            "S01E01",
            "--seed",
            "Anomalous carrier wave detected at the Europa Observatory Dome.",
            "--simulate-drift",
            "SC01_SH01",
        ]
    )
    assert exit_code == 0
    assert (
        tmp_path
        / "season_01"
        / "episode_01"
        / "editorial"
        / "Episode_S01E01_Assembly.otio"
    ).exists()
    assert (
        tmp_path
        / "season_01"
        / "episode_01"
        / "continuity"
        / "continuity_ledger.parquet"
    ).exists()
    assert (
        tmp_path
        / "season_01"
        / "episode_01"
        / "script"
        / "screenplay.fountain"
    ).exists()
