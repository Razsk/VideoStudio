# VideoStudio

**Architectural Blueprint for Automated Episodic Video Generation: End-to-End Narrative Synthesis, Continuity Tracking, and Production Orchestration**

`VideoStudio` implements a production-grade, dual-layer episodic video generation pipeline that unifies multi-agent narrative synthesis, GraphRAG lore tracking, Dual-Bridge visual continuity, keyframe-first diffusion gating, and OpenTimelineIO (`.otio`) editorial assembly.

---

## System Architecture

```text
+--------------------------------------------------------------------------------------------------+
|                                    TEMPORAL MACRO-ORCHESTRATOR                                   |
|                        (Durable State Execution, GPU Task Queues, Retries)                       |
+--------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+--------------------------------------------------------------------------------------------------+
|                                LANGGRAPH AGENT REASONING ENGINE                                  |
|                                                                                                  |
|  [Topic Research]   -->   [Director Agent]   -->   [Screenwriter]   -->   [Cinematographer]      |
|  (RAG / Lore Graph)       (Beat Sheets)            (ScreenJSON)           (Shot Lists)           |
|                                                           ^                      |               |
|                                                           |                      v               |
|                                                    [Semantic Loop] <---  [VLM Judge Gate]        |
+--------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+--------------------------------------------------------------------------------------------------+
|                               CONTINUITY & GENERATIVE MEDIA STACK                                |
|                                                                                                  |
|   Canonical Character Bibles   <--->   Continuity Ledger   <--->   Keyframe Synthesis            |
|   (Identity Invariants)                (Dynamic State)             (Shared-Attention Grids)      |
|                                                                          |                       |
|                                                                          v                       |
|   Editorial Assembly (OpenTimelineIO) <---------------------- Video Diffusion Generation         |
+--------------------------------------------------------------------------------------------------+
```

### Multi-Agent Role Specialization

| Agent Role | Primary Ingestion Source | Output Data Contract | Evaluation Metric / Gate |
| :--- | :--- | :--- | :--- |
| **Research / Lore** | User Prompt, GraphRAG Lore Base | `ThematicDossier` | Setting Adherence Score ($\ge 0.85$) |
| **Director** | `ThematicDossier`, Season Arc | 15-Beat Save the Cat / 8-Step Story Circle `BeatSheet` + `SceneCard`s | Pacing & Dramatic Curve + Causal Chain Verification |
| **Screenwriter** | `BeatSheet`, Character Canon | Standardized `ScreenJSONDocument` + `.fountain` Screenplay | Dialogue Naturalism & Observable-Only Action Linter |
| **Cinematographer** | `ScreenJSON` Scene Blocks | Draft 2020-12 `CinematicShotSpecification` + Parquet `ContinuityLedger` | Schema Linting & 180-Degree Axis Enforcement |
| **Continuity / Judge** | Candidate Keyframes, `ContinuityLedger` | `ContinuityVerdict` ($Score_{ID} \ge 0.85$) or `RevisionDelta` | Multi-Factored Identity, Wardrobe, Prop & Direction Gate |

---

## Deterministic Storage Hierarchy

```text
canon/
├── bible/
│   ├── characters/          # Frozen Character Bibles (invariant JSON dossiers, turnarounds, LoRAs)
│   └── locations/           # Persistent Location Bibles (spatial coordinates, architectural prompt cards)
└── lore_graph/              # GraphRAG property graph JSON + Neo4j Cypher dump (neo4j_dump.cypher)

season_01/episode_01/
├── script/                  # thematic_dossier.json, beat_sheet.json, screenplay.screen.json, screenplay.fountain
├── continuity/              # Apache Parquet continuity_ledger.parquet & JSON state mirror
├── storyboards/             # Validated shot_specifications.json, Shared-Attention Grids, keyframe plates, VLM audit
├── media/                   # Synthesized WAV dialogue stems & I2V master MP4 video clips
└── editorial/               # Episode_S01E01_Assembly.otio, workflow_history.jsonl, workflow_checkpoint.json
```

---

## Quick Start

### 1. Run the Automated 6-Phase Production Pipeline via CLI

```powershell
$env:PYTHONPATH="src"
python -m videostudio.cli produce --episode-id S01E01
```

### 2. Launch the Interactive Studio Production Control Room (Web UI & SSE Server)

```powershell
$env:PYTHONPATH="src"
python -m videostudio.cli serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` to:
- Dispatch episodic workflows with optional **Human Gate** pauses (`phase_1_narrative_arc`, `phase_2_dialogue_tone`)
- Trigger and observe the cyclical **Semantic Loop** when keyframe drift is detected by the **Continuity Judge Agent**
- Inspect **Shared-Attention Keyframe Grids** and per-shot `CinematicShotSpecification` schemas
- Trigger **Upstream Continuity Mutations** and verify automatic downstream invalidation and state reconciliation in the **Parquet Continuity Ledger**
- Inspect the **OpenTimelineIO** (`.otio`) multi-track assembly (`V1_Master_Video`, `A1_Dialogue`), cyan beat markers, and `generative_lineage` metadata

### 3. Run the Test Suite

```powershell
python -m pytest -v
```

---

## Documentation & Domain Model

- [`docs/USER_GUIDE.md`](./docs/USER_GUIDE.md) — Complete User Guide (CLI, Web Control Room, Human Gates, Canon authoring, Continuity Ledger & OpenTimelineIO)
- [`GLOSSARY.md`](./GLOSSARY.md) — Ubiquitous domain language for the studio
- [`AGENTS.md`](./AGENTS.md) — Module boundaries, seams, and Matt Pocock skills configuration
- [`docs/SPECIFICATION.md`](./docs/SPECIFICATION.md) — Full architectural specification
- [`docs/adr/`](./docs/adr/) — Architectural Decision Records (ADRs 0001–0004)
