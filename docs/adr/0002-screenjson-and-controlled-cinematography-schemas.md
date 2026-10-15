# ScreenJSON AST and Controlled Cinematography Schemas

We represent screenplays as strongly typed `ScreenJSON` abstract syntax trees with stable element UUIDs (exportable to industry-standard Fountain markup) and require all shot prompts to validate against the `CinematicShotSpecification` JSON Schema (Draft 2020-12) using controlled optical vocabularies instead of freeform prose prompts. Freeform prose causes structural hallucination during script parsing and optical ambiguity in video diffusion models.

## Consequences

- Action elements in `ScreenJSON` are validated to contain strictly observable, verb-centric present-tense visual and auditory events, rejecting un-filmable internal monologue.
- Camera framing, angle, movement, lens focal length, and frame rate are constrained to explicit enumerations, while scene-level lighting and color palettes lock at the `scene_heading` level and propagate across all shots in that scene.
