# VideoStudio

Automated episodic video production studio unifying multi-agent narrative synthesis, GraphRAG lore tracking, dual-bridge visual continuity, keyframe-first diffusion gating, and OpenTimelineIO editorial assembly.

## Language

### Orchestration & Agents

**Macro-Orchestrator**:
The durable workflow execution layer (powered by Temporal) that persists event histories, manages GPU task queues, and executes activities with automated exponential backoff retries and checkpointed failure-recovery boundaries.
_Avoid_: Cron runner, job scheduler, pipeline script

**Reasoning Graph**:
The stateful, cyclical directed graph (powered by LangGraph) that routes append-only narrative state across specialized cognitive agents, manages dynamic rollbacks, and streams real-time Server-Sent Events (SSE).
_Avoid_: Prompt chain, monolithic agent, chat loop

**Research and Lore Agent**:
The functional agent that queries the Lore Graph and vector store to compile a Thematic Dossier aligned with worldbuilding constraints and episodic goals.
_Avoid_: Summarizer, RAG bot

**Director Agent**:
The structural planning agent that transforms a Thematic Dossier and season arc into a 15-Beat Structural Outline (Save the Cat) or 8-Step Story Circle, balancing pacing and dramatic causality.
_Avoid_: Outliner, plot generator

**Screenwriter Agent**:
The dramatic writing agent that decomposes structural beats into causally linked Scene Cards and drafts standardized ScreenJSON screenplays with strictly observable visual and auditory actions.
_Avoid_: Dialogue writer, script formatter

**Cinematographer Agent**:
The camera artist agent that translates ScreenJSON scene blocks into validated Cinematic Shot Specifications using controlled optical vocabularies while enforcing the 180-degree rule.
_Avoid_: Prompt engineer, storyboarder

**Continuity Judge Agent**:
The multimodal verification agent (VLM Judge) that audits candidate keyframes against Character Bibles and the Continuity Ledger, emitting either an Acceptance Signal ($Score_{ID} \ge 0.85$) or a Revision Delta for the Semantic Loop.
_Avoid_: Quality filter, image classifier

**Semantic Loop**:
The cyclical feedback path triggered when the Continuity Judge Agent rejects a candidate keyframe, routing a Revision Delta with refined negative constraints or localized inpainting back to shot synthesis without regenerating the full sequence.
_Avoid_: Retry loop, full re-render

**Human Gate**:
An explicit operational checkpoint where execution pauses for human sign-off (Phase I narrative arc sign-off, Phase II dialogue and tone validation, and Phase VI final editorial playback).
_Avoid_: Manual override, debug pause

### Narrative & Screenplay Artifacts

**Thematic Dossier**:
The structured research output package defining episodic premise, tone, target conflicts, immutable facts, and a Setting Adherence Score.
_Avoid_: Research notes, prompt context

**Beat Sheet**:
A 15-beat (Save the Cat) or 8-step (Dan Harmon Story Circle) structural matrix mapping critical narrative pivots (such as Inciting Incident, Midpoint, and Dark Night of the Soul) before scene-level drafting begins.
_Avoid_: Chapter list, synopsis

**Scene Card**:
A self-contained dramatic unit decomposed from a structural beat, specifying dramatic objectives, active obstacles, character stakes, and causal initial/terminal states where Scene $N$'s terminal state directly informs Scene $N+1$'s initial state.
_Avoid_: Scene summary, vignette

**ScreenJSON**:
The abstract syntax tree (AST) screenplay serialization standard that assigns stable UUIDs to typed elements (`scene_heading`, `action`, `character`, `parenthetical`, `dialogue`, `transition`) for deterministic downstream consumption and Fountain export.
_Avoid_: Raw script text, markdown screenplay

### Continuity & Lore Representation

**Lore Graph**:
A hybrid GraphRAG knowledge base pairing a property graph (entities as nodes, temporally bounded narrative relationships as directed edges) with vector embeddings for tonal precedent retrieval.
_Avoid_: Vector database, lore document

**Character Bible**:
A frozen canonical production dossier encapsulating a character's unchanging identity invariants: bone structure, facial geometry, eye shape and color, ethnic phenotype, baseline hair texture, physical height, orthogonal turnaround plates, and fine-tuned LoRA weights.
_Avoid_: Character description, persona prompt

**Location Bible**:
A frozen canonical environment dossier containing spatial coordinate maps, architectural prompt cards, and base environment renders.
_Avoid_: Background description, setting note

**Dynamic Scene State**:
The temporary, mutable physical and environmental conditions governed by narrative progression—including emotional micro-expressions, posture, wardrobe variant, progressive wounds, grime, prop states, and lighting exposure—appended to Character Bible invariants at shot synthesis time.
_Avoid_: Character traits, static appearance

**Continuity Ledger**:
The explicit, append-only Parquet and JSON state graph tracking seven canonical parameters across sequential shots (`scene_shot_id`, `active_cast_wardrobe`, `dynamic_physical_state`, `prop_registry_affordance`, `spatial_screen_direction`, `lighting_environmental`, and `causal_reveal_flags`), where upstream modifications invalidate downstream dependent nodes.
_Avoid_: Shot log, context window history

**Causal Reveal Flag**:
A boolean or structured ledger marker recording disclosed secrets and observed events, restricting what characters can say or act upon at a given point in the narrative.
_Avoid_: Plot flag, memory tag

### Cinematography, Media & Editorial Interchange

**Cinematic Shot Specification**:
A strictly validated JSON Schema payload (`CinematicShotSpecification`) that parameterizes a single shot across `scene_context`, `subject`, `cinematography` (controlled optical enums for framing, angle, movement, and lens), `lighting_and_atmosphere`, `temporal_dynamics`, and `consistency_anchors`.
_Avoid_: Diffusion prompt, video prompt string

**Shared-Attention Keyframe Grid**:
A batched still-frame synthesis pass where sequential keyframes for a scene are generated together so cross-attention layers lock lighting, environmental geometry, and facial structure before any image-to-video motion diffusion occurs.
_Avoid_: Storyboard sketch, unconditioned frame

**Editorial Timeline**:
A multi-track OpenTimelineIO (`.otio`) container sequencing master video takes (`V1_Master_Video`) and synthesized dialogue/ambient audio stems (`A1_Dialogue`), annotated with cyan beat markers and embedded `generative_lineage` metadata (`prompt_uuid`, `model_version`, `seed`, `continuity_ledger_index`).
_Avoid_: Concatenated MP4, EDL text file
