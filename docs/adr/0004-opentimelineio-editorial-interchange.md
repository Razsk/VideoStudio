# OpenTimelineIO Editorial Interchange with Generative Lineage

We assemble episodic deliveries as multi-track OpenTimelineIO (`.otio`) project containers rather than flat concatenated video files, embedding `generative_lineage` metadata (`prompt_uuid`, `model_version`, `seed`, `continuity_ledger_index`) and cyan beat markers directly onto timeline clips.

## Consequences

- Non-linear editors (DaVinci Resolve, Final Cut Pro, Premiere) and DAWs can import the `.otio` timeline with separated `V1_Master_Video`, `A1_Dialogue`, and ambient audio tracks.
- Every rendered clip in the final assembly retains full deterministic traceability back to its originating `ScreenJSON` element, `CinematicShotSpecification`, diffusion seed, and Continuity Ledger row.
