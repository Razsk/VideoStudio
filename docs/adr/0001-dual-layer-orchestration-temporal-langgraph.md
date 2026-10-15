# Dual-Layer Orchestration with Temporal and LangGraph

We decouple macro-level infrastructure execution from micro-level cognitive agent reasoning by pairing a Temporal-compatible durable workflow engine (Macro-Orchestrator) with a LangGraph stateful cyclical reasoning graph (Reasoning Graph). Generative media synthesis (shared-attention keyframe grids, image-to-video diffusion, and audio synthesis) is compute-intensive and prone to rate limits and transient failures, whereas narrative critique and VLM continuity evaluation require agile, cyclical graph transitions and real-time Server-Sent Events (SSE) streaming.

## Consequences

- Every production phase executes as a checkpointed activity with exponential backoff retry guarantees and append-only event history persistence, preventing completed upstream work from re-running on failure.
- Cognitive agents operate over an append-only state dictionary inside the Reasoning Graph, supporting cyclical rollbacks via the Semantic Loop and human-in-the-loop sign-off at Human Gates.
