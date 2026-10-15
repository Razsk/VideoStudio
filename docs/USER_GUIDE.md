# VideoStudio User Guide

Welcome to **VideoStudio** — an end-to-end automated episodic video production studio that transforms story seeds and canonical world lore into multi-track **OpenTimelineIO (`.otio`)** editorial assemblies with verified visual and narrative continuity.

---

## Table of Contents

1. [Overview: The 6-Phase Production Pipeline](#1-overview-the-6-phase-production-pipeline)
2. [Installation & Setup](#2-installation--setup)
3. [Producing an Episode from the CLI](#3-producing-an-episode-from-the-cli)
4. [Using the Interactive Production Control Room (Web UI)](#4-using-the-interactive-production-control-room-web-ui)
5. [Human Verification Gates & Checkpoint Recovery](#5-human-verification-gates--checkpoint-recovery)
6. [Managing Canonical World Lore & Bibles](#6-managing-canonical-world-lore--bibles)
7. [Inspecting & Mutating the Continuity Ledger](#7-inspecting--mutating-the-continuity-ledger)
8. [Working with Output Artifacts (Fountain, Parquet & OpenTimelineIO)](#8-working-with-output-artifacts-fountain-parquet--opentimelineio)
9. [Python SDK & REST API Reference](#9-python-sdk--rest-api-reference)
10. [Troubleshooting Common Production Scenarios](#10-troubleshooting-common-production-scenarios)

---

## 1. Overview: The 6-Phase Production Pipeline

When you trigger an episodic run in VideoStudio, a **Macro-Orchestrator** (Temporal-compatible durable workflow runner) coordinates a **Reasoning Graph** (LangGraph cyclical multi-agent state machine) across six sequential phases:

| Phase | Active Agent / Engine | What Happens | Generated Artifacts |
| :--- | :--- | :--- | :--- |
| **I. Narrative Inception** | **Research & Lore Agent** + **Director Agent** | Queries the GraphRAG Lore Base for causal constraints and tonal precedents, then builds a **15-Beat Save the Cat** (or **8-Step Story Circle**) structural outline and causally linked **Scene Cards**. | `thematic_dossier.json`, `beat_sheet.json` |
| **II. Script & Continuity** | **Screenwriter Agent** | Drafts a typed **ScreenJSON** abstract syntax tree (AST) with stable UUIDs, strips un-filmable internal monologue via the observable-action linter, and exports industry-standard **Fountain (`.fountain`)** markup. | `screenplay.screen.json`, `screenplay.fountain` |
| **III. Cinematography** | **Cinematographer Agent** | Translates each scene into **Draft 2020-12 `CinematicShotSpecification`** JSON schemas using controlled optical vocabularies while locking scene lighting and enforcing the **180-degree cinematic rule** in the **Continuity Ledger**. | `shot_specifications.json`, `continuity_ledger.parquet` |
| **IV. Keyframe Synthesis & VLM Judge Gate** | **Shared-Attention Grid Synthesizer** + **Continuity Judge Agent** | Synthesizes `2x2` scene contact sheets and per-shot keyframes using **Dual-Bridge Prompts** (frozen Character Bible invariants + dynamic scene state). Audits each keyframe ($Score_{ID} \ge 0.85$); rejected frames loop through the **Semantic Loop** (`RevisionDelta`) until verified. | `SC*_shared_attention_grid.png`, `SC*_SH*_keyframe.png`, `vlm_audit_report.json` |
| **V. Motion Diffusion & Audio** | **I2V Motion Engine** + **TTS Synthesizer** | Enforces the **keyframe-first policy** (refusing to render video from unverified keyframes), generates master `.mp4` takes with frame-stepping inspection, and synthesizes `.wav` dialogue stems. | `SC*_SH*_master.mp4`, `SC*_SH*_dialogue.wav` |
| **VI. Editorial Assembly** | **OpenTimelineIO Builder** | Sequences master video takes (`V1_Master_Video`) and synchronized dialogue tracks (`A1_Dialogue`), attaches cyan beat markers and `generative_lineage` metadata, and writes the `.otio` timeline. | `Episode_<ID>_Assembly.otio`, `workflow_history.jsonl` |

---

## 2. Installation & Setup

### Prerequisites
- **Python 3.10+**

### Install Dependencies

From the repository root (`c:\Users\Benjamin Hinnum\VideoStudio`):

```powershell
python -m pip install -e ".[dev]"
```

Or install the core dependencies directly:

```powershell
python -m pip install pydantic jsonschema pyarrow opentimelineio fastapi uvicorn pytest httpx networkx pillow temporalio langgraph
```

### Verify Your Setup

Run the automated test suite to verify all schemas, GraphRAG queries, Parquet ledgers, keyframe synthesizers, and OpenTimelineIO exporters:

```powershell
python -m pytest -v
```

---

## 3. Producing an Episode from the CLI

You can run all six production phases directly from the terminal using the `produce` subcommand.

### Basic Command

```powershell
$env:PYTHONPATH="src"
python -m videostudio.cli produce --episode-id S01E01
```

### Customizing the Story Seed, Season Arc, and Drift Simulation

```powershell
$env:PYTHONPATH="src"
python -m videostudio.cli produce `
  --episode-id S01E02 `
  --season-arc "The Jovian Shadow Conspiracy" `
  --seed "Commander Elena Vance discovers that Dr. Marcus Koren's Chrono-Compass contains a hidden star chart pointing inside the Io plasma torus." `
  --simulate-drift "SC01_SH01,SC02_SH01"
```

#### CLI Options for `produce`
- `--root-dir <path>`: Root directory where `canon/` and `season_XX/episode_YY/` are stored (defaults to `.`).
- `--episode-id <SxxExx>`: Episode code formatted as `S01E01` (automatically maps to `season_01/episode_01/`).
- `--seed <text>`: The episode's narrative prompt or story seed.
- `--season-arc <text>`: Overarching season conflict injected into the Research & Lore Agent.
- `--simulate-drift <shot_ids>`: Comma-separated shot IDs (e.g., `SC01_SH01`) on which to simulate initial facial/identity drift so you can observe the **VLM Continuity Judge** reject the frame ($Score_{ID} < 0.85$) and trigger the **Semantic Loop** (`semantic_revision` $\rightarrow$ `keyframe_synthesis` $\rightarrow$ `vlm_judge`). Pass `""` to run with zero simulated drift.

---

## 4. Using the Interactive Production Control Room (Web UI)

VideoStudio includes a dark-mode **Production Control Room** dashboard served by FastAPI.

### Starting the Server

```powershell
$env:PYTHONPATH="src"
python -m videostudio.cli serve --host 127.0.0.1 --port 8000
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### Control Room Walkthrough

1. **Left Panel — 1. Dispatch Episodic Production**:
   - Enter your **Episode ID** (e.g., `S01E01`), **Season Arc**, and **Story Seed**.
   - Choose whether to run all 6 phases automatically or pause at a **Human Verification Gate** (`Phase I: Narrative Arc Sign-off` or `Phase II: Dialogue & Tone Validation`).
   - Click **Execute 6-Phase Production Pipeline**.
2. **Left Panel — 2. Upstream Continuity Mutation Test**:
   - Enter an upstream shot ID (e.g., `SC01_SH01`), a new physical trauma condition (e.g., `cryo_burn_left_wrist`), and an updated prop state (e.g., `cracked_azimuth_glass`).
   - Click **Mutate Upstream & Reconcile Ledger**. All downstream shots (`SC01_SH02`, `SC02_SH01`, etc.) are automatically invalidated and reconciled so progressive wounds and prop changes carry forward across the episode.
3. **Left Panel — 3. Live Reasoning Graph Audit Trail**:
   - Displays every LangGraph node execution in real time, including any cyclical **Semantic Loop** rollbacks.
4. **Right Panel — Inspection Tabs**:
   - **IV & V. Storyboards & VLM Judge**: View rendered keyframe plates, VLM identity similarity scores ($Score_{ID}$), optical lens/framing badges, and the raw `CinematicShotSpecification` JSON schemas.
   - **Continuity Ledger (Parquet)**: Inspect the 7 canonical continuity columns shot by shot.
   - **I & II. 15-Beat Sheet & ScreenJSON / Fountain**: Read the formatted `.fountain` screenplay, the 15-Beat Save the Cat outline, and the `ThematicDossier`.
   - **VI. OpenTimelineIO (`.otio`)**: Visualize the `V1_Master_Video` and `A1_Dialogue` timeline tracks, clip durations, cyan beat markers, diffusion seeds, and Continuity Ledger indices.
   - **GraphRAG Lore & Character Bibles**: Inspect frozen Character Bibles, temporal validity edges in the property graph, and the Neo4j Cypher export.

---

## 5. Human Verification Gates & Checkpoint Recovery

In production workflows, you often want a human showrunner or director to sign off on the narrative structure or screenplay before spending GPU compute on keyframe and video diffusion.

1. **Pausing at a Gate**:
   - Select **Pause at Phase I: Narrative Arc Sign-off** (or **Phase II: Dialogue & Tone Validation**) in the Web UI (or pass `pause_at_human_gate` to the API/orchestrator).
   - The orchestrator runs up to that phase, saves a durable checkpoint to `season_XX/episode_YY/editorial/workflow_checkpoint.json`, logs `HUMAN_GATE_PAUSED` in `workflow_history.jsonl`, and returns status `WAITING_FOR_HUMAN_GATE`.
2. **Reviewing & Editing Intermediate Artifacts**:
   - While paused, you can inspect `season_XX/episode_YY/script/beat_sheet.json` or `screenplay.fountain`.
3. **Approving & Resuming**:
   - Click **Approve Human Gate & Resume Checkpoint** in the Web UI (or call `POST /api/workflows/{workflow_id}/approve`).
   - The `DurableMacroOrchestrator` resumes from the checkpoint **without re-running completed upstream phases**.

---

## 6. Managing Canonical World Lore & Bibles

All persistent series lore lives under `canon/` at the root of your workspace:

### Adding or Editing a Character Bible (`canon/bible/characters/<CHAR_ID>/character_bible.json`)

Character Bibles store **Identity Invariants** ( unchanging physical anatomy, turnaround reference plates, and LoRA weights). Shot prompts never re-describe facial anatomy in freeform prose; they extract the frozen anchor from the Character Bible:

```json
{
  "character_id": "CHAR_ELENA_VANCE",
  "name": "Commander Elena Vance",
  "bone_structure": "High zygomatic arches, defined mandibular angle",
  "facial_geometry": "Oval-rectangular face, faint 12mm scar over left brow",
  "facial_proportions": "Balanced facial thirds, intercanthal distance 32mm",
  "eye_shape_and_color": "Almond-shaped slate-grey eyes with amber limbal ring",
  "ethnic_phenotype": "Northern Mediterranean / Nordic mix, olive-fair complexion",
  "baseline_hair_texture": "Coarse dark auburn hair braided tightly at nape",
  "physical_height": "176cm",
  "turnaround_plates": {
    "front": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_front.png",
    "angle_45": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_45.png",
    "profile": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_profile.png"
  },
  "lora_weights_uri": "canon/bible/characters/CHAR_ELENA_VANCE/elena_vance_v1.safetensors",
  "costume_variants": {
    "WARD_ELENA_EVA_TRENCH": "Weathered navy pressure-trench with brass collar seals",
    "WARD_ELENA_FLIGHT_DECK": "Charcoal utility jumpsuit with Helios Watch patch"
  },
  "voice_profile": "contralto_measured_urgent"
}
```

### Temporal Validity Edges in the GraphRAG Lore Base (`canon/lore_graph/property_graph.json`)

Relationships in the `LoreGraph` (`POSSESSES`, `KNOWS_SECRET`, `ALLIED_WITH`, `LOCATED_AT`, `RESTRICTED_BY`) include `valid_from_step` and `valid_to_step`. This prevents narrative anachronisms:
- If `CHAR_ELENA_VANCE` only has `KNOWS_SECRET -> SECRET_GHOST_TELEMETRY` starting at `valid_from_step: 2`, querying `graph.query_causal_constraints("CHAR_ELENA_VANCE", current_step=1)` guarantees she cannot act on or speak about that secret in Scene 1.

---

## 7. Inspecting & Mutating the Continuity Ledger

The **Continuity Ledger** (`season_XX/episode_YY/continuity/continuity_ledger.parquet` and `.json`) tracks seven canonical columns across every shot:

1. `scene_shot_id` (e.g., `SC01_SH01`)
2. `active_cast_wardrobe` (locks costume variants within scenes)
3. `dynamic_physical_state` (carries progressive wounds, sweat, frost, and grime forward across subsequent shots)
4. `prop_registry_affordance` (tracks held items and states like `opened_calibrated` or `cracked_lens`)
5. `spatial_screen_direction` (tracks `axis_id`, `camera_side`, `subject_facing`, and `eyeline_vector` to enforce the **180-degree cinematic rule**)
6. `lighting_environmental` (locks scene-heading illumination and color grading across all shots in a scene)
7. `causal_reveal_flags` (monotonically accumulates disclosed secrets and observed events)

### Reading the Parquet Ledger in Python

```python
import pyarrow.parquet as pq

table = pq.read_table("season_01/episode_01/continuity/continuity_ledger.parquet")
print(table.to_pydict())
```

---

## 8. Working with Output Artifacts (Fountain, Parquet & OpenTimelineIO)

After running `S01E01`, all generated files are organized under `season_01/episode_01/`:

- **Screenplay (`season_01/episode_01/script/`)**:
  - `screenplay.fountain`: Open in any Fountain-compatible screenwriting app (Highland, Fade In, Beat, or VS Code Fountain extension).
  - `screenplay.screen.json`: AST representation with element UUIDs.
- **Storyboards & Shot Schemas (`season_01/episode_01/storyboards/`)**:
  - `SC01_shared_attention_grid.png`, `SC02_shared_attention_grid.png`, `SC03_shared_attention_grid.png`: Shared-attention scene contact sheets.
  - `SC01_SH01_keyframe.png` ... `SC03_SH02_keyframe.png`: Individual verified shot keyframes with optical HUD overlays.
  - `shot_specifications.json`: Draft 2020-12 validated shot schemas.
  - `vlm_audit_report.json`: Full Continuity Judge scorecard.
- **Editorial Timeline (`season_01/episode_01/editorial/Episode_S01E01_Assembly.otio`)**:
  - Import `Episode_S01E01_Assembly.otio` directly into **DaVinci Resolve** (`File -> Import -> Timeline...`), **Final Cut Pro**, **Adobe Premiere Pro**, or inspect it via OpenTimelineIO's CLI tools (`otiocat`, `otioview`).
  - Every clip on `V1_Master_Video` carries `clip.metadata["generative_lineage"]` (`prompt_uuid`, `model_version`, `seed`, `continuity_ledger_index`) and a cyan beat marker (`Beat: Catalyst`, `Beat: Midpoint`, etc.).

---

## 9. Python SDK & REST API Reference

### Programmatic Python Usage

```python
from videostudio.storage import StudioStorage
from videostudio.orchestrator import DurableMacroOrchestrator

storage = StudioStorage(root_dir=".")
orchestrator = DurableMacroOrchestrator(storage=storage)

# Run full 6-phase workflow
run_state = orchestrator.execute_episode_workflow(
    episode_id="S01E01",
    story_seed="Anomalous carrier wave detected at the Helios Observatory Dome.",
    season_arc="The Jovian Shadow Conspiracy",
    simulate_drift_shots={"SC01_SH01"},
)

print("Status:", run_state.status)
print("OTIO Timeline:", run_state.otio_timeline_path)
```

### REST API Endpoints (`videostudio serve`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Interactive Production Control Room Web UI |
| `GET` | `/api/canon` | Returns Character Bibles, Location Bibles, GraphRAG JSON, and Neo4j Cypher |
| `POST` | `/api/lore/constraints` | Queries GraphRAG Causal Value Engine & vector tonal precedents |
| `POST` | `/api/workflows/run` | Starts a 6-phase episodic production workflow |
| `POST` | `/api/workflows/{workflow_id}/approve` | Approves a paused Human Gate and resumes from checkpoint |
| `GET` | `/api/workflows/{workflow_id}/stream` | Streams Server-Sent Events (`text/event-stream`) for node transitions |
| `GET` | `/api/episodes/{episode_id}/artifacts` | Returns all generated artifacts, ledger rows, and timeline summary |
| `POST` | `/api/continuity/mutate` | Mutates an upstream shot in the Continuity Ledger and reconciles downstream state |
| `GET` | `/files/{file_path:path}` | Serves generated PNG keyframes, WAV stems, MP4 clips, and `.otio` files |

---

## 10. Troubleshooting Common Production Scenarios

- **`180-degree axis violation between SC01_SH01 and SC01_SH02`**:
  - **Cause**: Two sequential shots in the same scene flipped `camera_side` (e.g., `north_of_axis` $\rightarrow$ `south_of_axis`) on the same `axis_id` without a motivating camera movement (`axis_reestablished_by_movement=True`).
  - **Fix**: Keep `camera_side` consistent across reverse-angle cuts within a scene, or set `axis_reestablished_by_movement=True` on an `arc` / `tracking` shot that explicitly crosses the line.
- **`Keyframe-first policy violation: cannot dispatch I2V motion diffusion`**:
  - **Cause**: `synthesize_i2v_motion_clip` was called with a keyframe that has `verified=False` or `identity_score < 0.85`.
  - **Fix**: Pass the rejected keyframe's `RevisionDelta` through `apply_revision_delta_to_shot()`, re-synthesize the keyframe, and re-verify with `VLMContinuityJudge` before running I2V diffusion.
- **`ValidationError` on `CinematicShotSpecification`**:
  - **Cause**: A shot prompt used an unlisted optical value (e.g., `"framing": "ultra_close"` or `"frame_rate": 25`).
  - **Fix**: Use only the controlled vocabularies defined in [`videostudio.schemas`](../src/videostudio/schemas.py) (`FramingScale`, `CameraAngle`, `CameraMovement`, `LensFocalLength`, and frame rates `24`, `30`, or `60`).
