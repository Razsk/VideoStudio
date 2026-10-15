# Dual-Bridge Continuity, Parquet Ledger, and Keyframe-First Verification

We separate invariant character identity (frozen in Character Bibles with orthogonal turnarounds and LoRA anchors) from mutable Dynamic Scene State tracked in an append-only Parquet Continuity Ledger, and enforce a keyframe-first verification gate ($Score_{ID} \ge 0.85$) before dispatching image-to-video (I2V) motion diffusion.

## Consequences

- Shot prompts never re-describe baseline facial anatomy in prose; they reference canonical Character Bible anchors and append only the current shot's Dynamic Scene State.
- The Continuity Ledger forms a directed state graph: mutating any upstream scene automatically invalidates downstream ledger entries and runs a state reconciliation pass (propagating progressive wounds, prop states, 180-degree screen direction, and Causal Reveal Flags).
- Candidate keyframes are synthesized in Shared-Attention Keyframe Grids and audited by the Continuity Judge Agent; rejected frames route through the Semantic Loop for localized inpainting or negative-constraint refinement rather than wasting compute on unverified video generation.
