# AGENTS.md

## Architecture Overview

`VideoStudio` implements the **Architectural Blueprint for Automated Episodic Video Generation: End-to-End Narrative Synthesis, Continuity Tracking, and Production Orchestration**.

Always consult [`GLOSSARY.md`](./GLOSSARY.md) for canonical terminology and [`docs/adr/`](./docs/adr/) for architectural decisions before modifying modules or writing tests.

### Deep Modules & Seams

1. **`videostudio.schemas`** — Strongly typed Pydantic models and JSON Schema (Draft 2020-12) validators for `ThematicDossier`, `BeatSheet` (15-Beat Save the Cat & 8-Step Story Circle), `SceneCard`, `ScreenJSON` (with Fountain `.fountain` export and observable-action linting), and `CinematicShotSpecification`.
2. **`videostudio.lore`** — Hybrid **Lore Graph** (GraphRAG property graph with temporal validity edges + vector similarity search) and frozen canonical **Character Bibles** (`canon/bible/characters/`) and **Location Bibles** (`canon/bible/locations/`).
3. **`videostudio.continuity`** — Append-only **Continuity Ledger** persisted to Parquet (`pyarrow`) and JSON (`season_XX/episode_YY/continuity/`), enforcing the 7 canonical ledger columns, 180-degree cinematic axis validation, Dual-Bridge prompt composition, and upstream invalidation / state reconciliation.
4. **`videostudio.agents`** — Role-specialized multi-agent system (**Research and Lore Agent**, **Director Agent**, **Screenwriter Agent**, **Cinematographer Agent**, **Continuity Judge Agent**) orchestrated by the **Reasoning Graph** (LangGraph cyclical state graph with **Semantic Loop** rollback, **Human Gate** checkpoints, and Server-Sent Events streaming).
5. **`videostudio.media`** — **Shared-Attention Keyframe Grid** synthesizer (`2x2` scene contact sheets + per-shot keyframe plates), image-to-video (I2V) motion diffusion engine with automated frame-stepping inspection, and TTS dialogue / ambient audio stem synthesizer.
6. **`videostudio.editorial`** — **Editorial Timeline** builder (`construct_editorial_timeline`) producing standard OpenTimelineIO (`.otio`) multi-track containers with cyan beat markers and `generative_lineage` clip metadata.
7. **`videostudio.orchestrator`** — **Macro-Orchestrator** providing Temporal workflow/activity definitions alongside a deterministic local durable execution runner with append-only event history, checkpoint recovery, and exponential backoff retries.
8. **`videostudio.storage`** — Content-addressed repository manager enforcing the canonical `canon/` and `season_XX/episode_YY/` directory hierarchy.
9. **`videostudio.server` & `videostudio.cli`** — FastAPI backend with real-time SSE streaming and an interactive Studio Web UI dashboard, plus CLI entry points.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (`Razsk/VideoStudio`). See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five canonical triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`GLOSSARY.md` at the repo root and ADRs in `docs/adr/`). See `docs/agents/domain.md`.
