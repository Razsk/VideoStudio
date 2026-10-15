from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from videostudio.continuity import ContinuityLedger
from videostudio.llm import (
    DEFAULT_MODELS,
    SUGGESTED_MODELS,
    LLMConfig,
    LLMProviderType,
    SecureCredentialStore,
)
from videostudio.lore import seed_default_canon
from videostudio.orchestrator import DurableMacroOrchestrator
from videostudio.storage import StudioStorage


class RunWorkflowRequest(BaseModel):
    episode_id: str = "S01E01"
    story_seed: str = (
        "An encrypted harmonic from decommissioned Beacon 9 forces Commander Elena Vance "
        "and Dr. Marcus Koren into the Sub-Level 4 Cryogenic Relay Vault."
    )
    season_arc: str = "The Jovian Shadow Conspiracy"
    simulate_drift_shots: List[str] = Field(default_factory=lambda: ["SC01_SH01"])
    pause_at_human_gate: Optional[
        Literal[
            "phase_1_narrative_arc",
            "phase_2_dialogue_tone",
            "phase_6_final_playback",
        ]
    ] = None
    llm_provider: LLMProviderType = "deterministic"
    llm_model: Optional[str] = None


class SetCredentialRequest(BaseModel):
    provider: Literal["openrouter", "gemini", "openai", "anthropic"]
    api_key: str = Field(..., min_length=8)


class ApproveGateRequest(BaseModel):
    gate_name: str
    reviewer_notes: str = "Approved by Human Director"


class LoreQueryRequest(BaseModel):
    character_id: str = "CHAR_ELENA_VANCE"
    step: int = 2
    query: str = "tactile brass observatory chiaroscuro"


class MutateLedgerRequest(BaseModel):
    episode_id: str = "S01E01"
    scene_shot_id: str = "SC01_SH01"
    added_physical_state: Dict[str, List[str]] = Field(default_factory=dict)
    updated_props: Dict[str, str] = Field(default_factory=dict)
    added_reveal_flags: List[str] = Field(default_factory=list)
    reconcile: bool = True


STUDIO_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>VideoStudio — Automated Episodic Production Control Room</title>
  <style>
    :root {
      --bg: #0b0f17;
      --panel: #131b29;
      --border: #22314a;
      --accent: #38bdf8;
      --accent-amber: #f59e0b;
      --success: #22c55e;
      --danger: #ef4444;
      --text: #e2e8f0;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      padding: 18px 28px;
      border-bottom: 1px solid var(--border);
      background: #0e1522;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    header h1 {
      margin: 0;
      font-size: 1.25rem;
      letter-spacing: 0.02em;
      color: var(--accent);
    }
    .badge {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      background: rgba(56, 189, 248, 0.14);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.35);
    }
    main {
      max-width: 1480px;
      margin: 0 auto;
      padding: 22px 28px;
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 22px;
    }
    @media (max-width: 1024px) {
      main { grid-template-columns: 1fr; }
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin-bottom: 18px;
    }
    .card h2 {
      margin-top: 0;
      font-size: 1rem;
      color: var(--accent);
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }
    label {
      display: block;
      font-size: 0.82rem;
      color: var(--muted);
      margin-bottom: 4px;
      margin-top: 10px;
    }
    input, textarea, select {
      width: 100%;
      padding: 8px 10px;
      background: #0b111c;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.88rem;
    }
    textarea { min-height: 76px; resize: vertical; }
    button {
      margin-top: 14px;
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      background: var(--accent);
      color: #06101b;
      width: 100%;
    }
    button.secondary {
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--border);
    }
    button.amber {
      background: var(--accent-amber);
      color: #0b0f17;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .tab-btn {
      width: auto;
      margin-top: 0;
      padding: 7px 14px;
      background: #0e1522;
      color: var(--muted);
      border: 1px solid var(--border);
    }
    .tab-btn.active {
      background: var(--accent);
      color: #06101b;
      border-color: var(--accent);
    }
    pre {
      background: #080c13;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      overflow-x: auto;
      font-size: 0.8rem;
      max-height: 440px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    th, td {
      border: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }
    th { background: #0e1522; color: var(--accent); }
    .grid-gallery {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 14px;
    }
    .shot-card {
      background: #0c121d;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
    }
    .shot-card img {
      width: 100%;
      border-radius: 5px;
      border: 1px solid var(--border);
    }
    .timeline-track {
      background: #090e17;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      margin-bottom: 10px;
    }
    .clip-row {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding-top: 6px;
    }
    .clip-pill {
      background: rgba(56, 189, 248, 0.16);
      border: 1px solid var(--accent);
      border-radius: 5px;
      padding: 8px 10px;
      min-width: 165px;
      font-size: 0.78rem;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>VIDEOSTUDIO // DUAL-LAYER EPISODIC PRODUCTION ORCHESTRATOR</h1>
      <div style="font-size:0.8rem;color:var(--muted);">
        Temporal Macro-Orchestrator + LangGraph Reasoning Engine + GraphRAG Lore + Parquet Continuity Ledger + OpenTimelineIO
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      <span class="badge" id="wf-status-badge">IDLE</span>
    </div>
  </header>

  <main>
    <section>
      <div class="card">
        <h2>0. Secure LLM Engine & OpenRouter Configuration</h2>
        <div style="font-size:0.78rem;color:var(--muted);">
          API keys are held strictly in server memory (<code>SecretStr</code>) or loaded from <code>.env</code>. Keys are never written to checkpoints, logs, or browser storage.
        </div>
        <label>LLM Provider</label>
        <select id="llm-provider" onchange="onProviderChange()">
          <option value="openrouter">OpenRouter (Unified Multi-Model Gateway)</option>
          <option value="gemini">Google Gemini</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic Claude</option>
          <option value="ollama">Ollama (Local Loopback Only)</option>
          <option value="deterministic" selected>Deterministic Offline Reference Engine</option>
        </select>
        <label>Model Identifier</label>
        <input id="llm-model" list="model-suggestions" value="deterministic-reference-v1" />
        <datalist id="model-suggestions"></datalist>
        <div id="cred-box" style="margin-top:8px;padding:10px;background:#090e17;border:1px solid var(--border);border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.78rem;">
            <span>Credential Status:</span>
            <span id="cred-status" style="color:var(--accent);font-weight:600;">Checking...</span>
          </div>
          <label style="margin-top:8px;">Set Session API Key (write-only, never stored in browser)</label>
          <input id="llm-api-key" type="password" autocomplete="off" spellcheck="false" placeholder="sk-or-v1-... (cleared immediately on save)" />
          <button class="secondary" style="margin-top:8px;padding:7px 12px;" onclick="saveSessionKey()">Save Key to Secure Server Memory</button>
        </div>
      </div>

      <div class="card">
        <h2>1. Dispatch Episodic Production</h2>
        <label>Episode ID</label>
        <input id="episode-id" value="S01E01" />
        <label>Season Arc</label>
        <input id="season-arc" value="The Jovian Shadow Conspiracy" />
        <label>Story Seed</label>
        <textarea id="story-seed">An encrypted harmonic from decommissioned Beacon 9 forces Commander Elena Vance and Dr. Marcus Koren into the Sub-Level 4 Cryogenic Relay Vault.</textarea>
        <label>Simulate Initial Drift (triggers VLM Judge Semantic Loop)</label>
        <input id="drift-shots" value="SC01_SH01" />
        <label>Human Verification Gate Checkpoint</label>
        <select id="human-gate">
          <option value="">Run All 6 Phases Automatically</option>
          <option value="phase_1_narrative_arc">Pause at Phase I: Narrative Arc Sign-off</option>
          <option value="phase_2_dialogue_tone">Pause at Phase II: Dialogue & Tone Validation</option>
        </select>
        <button onclick="runWorkflow()">Execute 6-Phase Production Pipeline</button>
        <div id="gate-box" style="display:none;margin-top:12px;padding:10px;border:1px solid var(--accent-amber);border-radius:6px;">
          <div style="font-size:0.82rem;color:var(--accent-amber);font-weight:600;" id="gate-label">Human Gate Paused</div>
          <input id="gate-notes" value="Approved: Pacing and dramatic reversals verified." style="margin-top:6px;" />
          <button class="amber" onclick="approveGate()">Approve Human Gate & Resume Checkpoint</button>
        </div>
      </div>

      <div class="card">
        <h2>2. Upstream Continuity Mutation Test</h2>
        <div style="font-size:0.78rem;color:var(--muted);">
          Mutate an upstream scene node in the Continuity Ledger to trigger downstream invalidation and state graph reconciliation.
        </div>
        <label>Upstream Shot ID</label>
        <input id="mut-shot" value="SC01_SH01" />
        <label>Added Physical Trauma (CHAR_ELENA_VANCE)</label>
        <input id="mut-trauma" value="cryo_burn_left_wrist" />
        <label>Updated Prop State (ART_CHRONO_COMPASS)</label>
        <input id="mut-prop" value="cracked_azimuth_glass" />
        <button class="secondary" onclick="mutateLedger()">Mutate Upstream & Reconcile Ledger</button>
      </div>

      <div class="card">
        <h2>3. Live Reasoning Graph Audit Trail</h2>
        <div id="audit-trail" style="font-size:0.8rem;max-height:280px;overflow-y:auto;"></div>
      </div>
    </section>

    <section>
      <div class="tabs">
        <button class="tab-btn active" onclick="showTab('tab-storyboards', this)">IV & V. Storyboards & VLM Judge</button>
        <button class="tab-btn" onclick="showTab('tab-ledger', this)">Continuity Ledger (Parquet)</button>
        <button class="tab-btn" onclick="showTab('tab-script', this)">I & II. 15-Beat Sheet & ScreenJSON / Fountain</button>
        <button class="tab-btn" onclick="showTab('tab-otio', this)">VI. OpenTimelineIO (.otio)</button>
        <button class="tab-btn" onclick="showTab('tab-canon', this)">GraphRAG Lore & Character Bibles</button>
      </div>

      <div id="tab-storyboards" class="card">
        <h2>Shared-Attention Keyframe Grids, VLM Continuity Verdicts & Shot Schemas</h2>
        <div id="storyboard-content">Run the pipeline to inspect generated Shared-Attention Keyframe Grids and VLM Judge scores.</div>
      </div>

      <div id="tab-ledger" class="card" style="display:none;">
        <h2>Episodic Continuity Ledger (7 Canonical Columns)</h2>
        <div id="ledger-content"></div>
      </div>

      <div id="tab-script" class="card" style="display:none;">
        <h2>Narrative Decomposition: Thematic Dossier, 15-Beat Matrix, ScreenJSON & Fountain</h2>
        <div id="script-content"></div>
      </div>

      <div id="tab-otio" class="card" style="display:none;">
        <h2>OpenTimelineIO Master Assembly (V1_Master_Video & A1_Dialogue)</h2>
        <div id="otio-content"></div>
      </div>

      <div id="tab-canon" class="card" style="display:none;">
        <h2>Canonical Character Bibles, Location Bibles & GraphRAG Property Graph</h2>
        <div id="canon-content"></div>
      </div>
    </section>
  </main>

  <script>
    let currentWorkflowId = null;
    let currentPendingGate = null;
    let llmProvidersMeta = null;

    async function loadLLMProviders() {
      const res = await fetch('/api/llm/providers');
      if (!res.ok) return;
      llmProvidersMeta = await res.json();
      onProviderChange();
    }

    function onProviderChange() {
      if (!llmProvidersMeta) return;
      const provider = document.getElementById('llm-provider').value;
      const modelInput = document.getElementById('llm-model');
      const datalist = document.getElementById('model-suggestions');
      const suggested = (llmProvidersMeta.suggested_models && llmProvidersMeta.suggested_models[provider]) || [];
      datalist.innerHTML = suggested.map(m => `<option value="${m}"></option>`).join('');
      if (llmProvidersMeta.default_models && llmProvidersMeta.default_models[provider]) {
        modelInput.value = llmProvidersMeta.default_models[provider];
      }
      const pStatus = llmProvidersMeta.providers && llmProvidersMeta.providers[provider];
      const statusEl = document.getElementById('cred-status');
      if (pStatus) {
        statusEl.textContent = pStatus.configured ? `READY (${pStatus.masked_key})` : 'MISSING KEY';
        statusEl.style.color = pStatus.configured ? 'var(--success)' : 'var(--accent-amber)';
      }
    }

    async function saveSessionKey() {
      const provider = document.getElementById('llm-provider').value;
      const keyInput = document.getElementById('llm-api-key');
      const api_key = keyInput.value.trim();
      keyInput.value = '';
      if (!api_key) return;
      const res = await fetch('/api/llm/credentials', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({provider, api_key})
      });
      if (res.ok) {
        await loadLLMProviders();
      }
    }

    function showTab(tabId, btn) {
      for (const id of ['tab-storyboards','tab-ledger','tab-script','tab-otio','tab-canon']) {
        document.getElementById(id).style.display = (id === tabId) ? 'block' : 'none';
      }
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }

    async function loadCanon() {
      const res = await fetch('/api/canon');
      const data = await res.json();
      document.getElementById('canon-content').innerHTML = `
        <h3>Canonical Character Bibles (Identity Invariants)</h3>
        <pre>${JSON.stringify(data.characters, null, 2)}</pre>
        <h3>GraphRAG Property Graph (Temporal Validity Edges)</h3>
        <pre>${JSON.stringify(data.lore_graph, null, 2)}</pre>
        <h3>Neo4j Cypher Dump</h3>
        <pre>${data.neo4j_cypher}</pre>
      `;
    }

    async function runWorkflow() {
      const episode_id = document.getElementById('episode-id').value.trim();
      const season_arc = document.getElementById('season-arc').value.trim();
      const story_seed = document.getElementById('story-seed').value.trim();
      const driftRaw = document.getElementById('drift-shots').value.trim();
      const pause_at_human_gate = document.getElementById('human-gate').value || null;
      const llm_provider = document.getElementById('llm-provider').value;
      const llm_model = document.getElementById('llm-model').value.trim() || null;
      const simulate_drift_shots = driftRaw ? driftRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

      document.getElementById('wf-status-badge').textContent = 'RUNNING...';
      const res = await fetch('/api/workflows/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          episode_id,
          story_seed,
          season_arc,
          simulate_drift_shots,
          pause_at_human_gate,
          llm_provider,
          llm_model
        })
      });
      const data = await res.json();
      handleWorkflowResponse(data);
    }

    async function approveGate() {
      if (!currentWorkflowId || !currentPendingGate) return;
      const reviewer_notes = document.getElementById('gate-notes').value;
      const res = await fetch(`/api/workflows/${currentWorkflowId}/approve`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({gate_name: currentPendingGate, reviewer_notes})
      });
      const data = await res.json();
      handleWorkflowResponse(data);
    }

    async function handleWorkflowResponse(data) {
      currentWorkflowId = data.workflow_id;
      currentPendingGate = data.pending_gate;
      document.getElementById('wf-status-badge').textContent = data.status;

      const gateBox = document.getElementById('gate-box');
      if (data.status === 'WAITING_FOR_HUMAN_GATE') {
        gateBox.style.display = 'block';
        document.getElementById('gate-label').textContent = 'Paused at Human Gate: ' + data.pending_gate;
      } else {
        gateBox.style.display = 'none';
      }

      const trail = (data.graph_state && data.graph_state.audit_trail) || [];
      document.getElementById('audit-trail').innerHTML = trail.map(ev => `
        <div style="padding:6px 0;border-bottom:1px solid var(--border);">
          <strong style="color:var(--accent)">[${ev.phase}]</strong> <code>${ev.node}</code><br/>
          <span>${ev.detail}</span>
        </div>
      `).join('');

      await refreshEpisodeArtifacts(data.episode_id);
    }

    async function refreshEpisodeArtifacts(episodeId) {
      const res = await fetch(`/api/episodes/${episodeId}/artifacts`);
      if (!res.ok) return;
      const art = await res.json();

      // Storyboards & VLM Judge
      const kfList = art.keyframes || [];
      const shotsMap = {};
      (art.shot_specs || []).forEach(s => { shotsMap[s.shot_id] = s; });
      document.getElementById('storyboard-content').innerHTML = `
        <div style="margin-bottom:12px;font-size:0.85rem;">
          <strong>Semantic Loop Iterations:</strong> ${art.semantic_loop_iterations || 0} |
          <strong>Verified Keyframes:</strong> ${kfList.filter(k => k.verified).length} / ${kfList.length}
        </div>
        <div class="grid-gallery">
          ${kfList.map(k => {
            const sh = shotsMap[k.shot_id] || {};
            return `<div class="shot-card">
              <img src="/files/${k.image_path}?t=${Date.now()}" alt="${k.shot_id}" />
              <div style="margin-top:8px;font-weight:600;color:var(--accent);">${k.shot_id} — Score_ID: ${k.identity_score}</div>
              <div style="font-size:0.76rem;color:var(--muted);">
                ${sh.cinematography ? `${sh.cinematography.framing} | ${sh.cinematography.camera_angle} | ${sh.cinematography.lens}` : ''}
              </div>
              <div style="font-size:0.78rem;margin-top:4px;">${sh.subject ? sh.subject.action_core : ''}</div>
            </div>`;
          }).join('')}
        </div>
        <h3 style="margin-top:18px;">Validated CinematicShotSpecification JSON Schemas</h3>
        <pre>${JSON.stringify(art.shot_specs, null, 2)}</pre>
      `;

      // Continuity Ledger
      const entries = art.ledger_entries || [];
      document.getElementById('ledger-content').innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Shot ID</th>
              <th>Active Cast & Wardrobe</th>
              <th>Dynamic Physical State</th>
              <th>Prop Registry & Affordance</th>
              <th>Spatial / 180° Direction</th>
              <th>Lighting & Env</th>
              <th>Causal Reveal Flags</th>
            </tr>
          </thead>
          <tbody>
            ${entries.map(e => `
              <tr>
                <td><strong>${e.scene_shot_id}</strong></td>
                <td><pre style="margin:0">${JSON.stringify(e.active_cast_wardrobe, null, 1)}</pre></td>
                <td><pre style="margin:0">${JSON.stringify(e.dynamic_physical_state, null, 1)}</pre></td>
                <td><pre style="margin:0">${JSON.stringify(e.prop_registry_affordance, null, 1)}</pre></td>
                <td>${e.spatial_screen_direction.subject_facing}<br/><small>${e.spatial_screen_direction.camera_side}</small></td>
                <td><small>${e.lighting_environmental.lighting_setup || ''} / ${e.lighting_environmental.weather || ''}</small></td>
                <td>${(e.causal_reveal_flags || []).join(', ')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      // Script
      document.getElementById('script-content').innerHTML = `
        <h3>Fountain Screenplay Export (.fountain)</h3>
        <pre>${art.fountain_script || ''}</pre>
        <h3>15-Beat Save the Cat Structural Matrix</h3>
        <pre>${JSON.stringify(art.beat_sheet, null, 2)}</pre>
        <h3>Thematic Dossier</h3>
        <pre>${JSON.stringify(art.thematic_dossier, null, 2)}</pre>
      `;

      // OTIO
      const tl = art.timeline_summary || {};
      document.getElementById('otio-content').innerHTML = `
        <div style="margin-bottom:12px;">
          <strong>Timeline:</strong> ${tl.name || 'N/A'} |
          <strong>Total Clips:</strong> ${tl.total_clips || 0} |
          <strong>Duration:</strong> ${tl.total_duration_seconds || 0}s (24 fps)
        </div>
        ${(tl.tracks || []).map(tr => `
          <div class="timeline-track">
            <strong>${tr.name}</strong> <span style="color:var(--muted);font-size:0.78rem;">(${tr.kind})</span>
            <div class="clip-row">
              ${(tr.items || []).map(it => `
                <div class="clip-pill">
                  <strong>${it.name || it.type}</strong> (${it.duration_seconds}s)<br/>
                  ${it.markers && it.markers.length ? `<span style="color:var(--accent)">${it.markers[0].name}</span><br/>` : ''}
                  ${it.generative_lineage ? `<small>seed: ${it.generative_lineage.seed || ''} | idx: ${it.generative_lineage.continuity_ledger_index}</small>` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
        <h3>Raw OpenTimelineIO Summary</h3>
        <pre>${JSON.stringify(tl, null, 2)}</pre>
      `;
    }

    async function mutateLedger() {
      const episode_id = document.getElementById('episode-id').value.trim();
      const scene_shot_id = document.getElementById('mut-shot').value.trim();
      const trauma = document.getElementById('mut-trauma').value.trim();
      const propState = document.getElementById('mut-prop').value.trim();
      const res = await fetch('/api/continuity/mutate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          episode_id,
          scene_shot_id,
          added_physical_state: {"CHAR_ELENA_VANCE": [trauma]},
          updated_props: {"ART_CHRONO_COMPASS": propState},
          added_reveal_flags: ["UPSTREAM_MUTATION_RECONCILED"],
          reconcile: true
        })
      });
      if (res.ok) {
        await refreshEpisodeArtifacts(episode_id);
      }
    }

    loadCanon();
    loadLLMProviders();
  </script>
</body>
</html>
"""


def create_app(root_dir: Path | str = ".") -> FastAPI:
    storage = StudioStorage(root_dir=root_dir)
    lore_graph = seed_default_canon(storage)
    sse_events: List[Dict[str, Any]] = []
    credential_store = SecureCredentialStore(dotenv_paths=[storage.root_dir / ".env"])

    orchestrator = DurableMacroOrchestrator(
        storage=storage,
        event_callback=lambda ev: sse_events.append(ev),
        credential_store=credential_store,
    )

    app = FastAPI(
        title="VideoStudio Automated Episodic Video Generation API",
        version="1.0.0",
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(content=STUDIO_DASHBOARD_HTML)

    @app.get("/api/llm/providers")
    def get_llm_providers() -> Dict[str, Any]:
        return {
            "providers": credential_store.get_provider_status(),
            "default_models": DEFAULT_MODELS,
            "suggested_models": SUGGESTED_MODELS,
        }

    @app.post("/api/llm/credentials")
    def set_llm_credential(req: SetCredentialRequest) -> Dict[str, Any]:
        try:
            credential_store.set_session_key(req.provider, req.api_key)
            return credential_store.get_provider_status()[req.provider]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/canon")
    def get_canon() -> Dict[str, Any]:
        chars = [c.model_dump() for c in storage.list_character_bibles()]
        locs = [loc.model_dump() for loc in storage.list_location_bibles()]
        graph = storage.load_lore_graph()
        return {
            "characters": chars,
            "locations": locs,
            "lore_graph": graph.to_dict(),
            "neo4j_cypher": graph.to_neo4j_cypher(),
        }

    @app.post("/api/lore/constraints")
    def query_lore_constraints(req: LoreQueryRequest) -> Dict[str, Any]:
        graph = storage.load_lore_graph()
        constraints = graph.query_causal_constraints(req.character_id, req.step)
        precedents = graph.retrieve_tonal_precedents(req.query, top_k=2)
        return {
            "constraints": constraints,
            "tonal_precedents": precedents,
        }

    @app.post("/api/workflows/run")
    def run_workflow(req: RunWorkflowRequest) -> Dict[str, Any]:
        llm_config = LLMConfig(
            provider=req.llm_provider,
            model=req.llm_model or DEFAULT_MODELS[req.llm_provider],
        )
        run_state = orchestrator.execute_episode_workflow(
            episode_id=req.episode_id,
            story_seed=req.story_seed,
            season_arc=req.season_arc,
            simulate_drift_shots=set(req.simulate_drift_shots),
            pause_at_human_gate=req.pause_at_human_gate,
            llm_config=llm_config,
        )
        return run_state.model_dump()

    @app.post("/api/workflows/{workflow_id}/approve")
    def approve_gate(workflow_id: str, req: ApproveGateRequest) -> Dict[str, Any]:
        try:
            run_state = orchestrator.approve_human_gate_and_resume(
                workflow_id=workflow_id,
                gate_name=req.gate_name,
                reviewer_notes=req.reviewer_notes,
            )
            return run_state.model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workflows/{workflow_id}/stream")
    async def stream_workflow_events(workflow_id: str) -> StreamingResponse:
        async def event_generator():
            run_state = orchestrator.get_run(workflow_id)
            for ev in run_state.graph_state.get("audit_trail", []):
                yield f"data: {json.dumps(ev)}\n\n"
                await asyncio.sleep(0.01)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/api/episodes/{episode_id}/artifacts")
    def get_episode_artifacts(episode_id: str) -> Dict[str, Any]:
        season, episode = storage.parse_episode_id(episode_id)
        ep_dirs = storage.ensure_episode_directories(season, episode)

        ckpt_file = ep_dirs["editorial"] / "workflow_checkpoint.json"
        graph_state: Dict[str, Any] = {}
        if ckpt_file.exists():
            ckpt_data = json.loads(ckpt_file.read_text(encoding="utf-8"))
            graph_state = ckpt_data.get("graph_state", {})

        pq_file = ep_dirs["continuity"] / "continuity_ledger.parquet"
        ledger_entries: List[Dict[str, Any]] = []
        if pq_file.exists():
            ledger = ContinuityLedger.load_parquet(pq_file, episode_id=episode_id)
            ledger_entries = [e.model_dump() for e in ledger.entries]

        return {
            "episode_id": episode_id,
            "thematic_dossier": graph_state.get("thematic_dossier"),
            "beat_sheet": graph_state.get("beat_sheet"),
            "screenjson": graph_state.get("screenjson"),
            "fountain_script": graph_state.get("fountain_script"),
            "shot_specs": graph_state.get("shot_specs", []),
            "keyframes": graph_state.get("keyframes", []),
            "verdicts": graph_state.get("verdicts", []),
            "semantic_loop_iterations": graph_state.get("semantic_loop_iterations", 0),
            "ledger_entries": ledger_entries,
            "timeline_summary": graph_state.get("timeline_summary"),
            "workflow_history": orchestrator.load_workflow_history(season, episode),
        }

    @app.post("/api/continuity/mutate")
    def mutate_continuity_ledger(req: MutateLedgerRequest) -> Dict[str, Any]:
        season, episode = storage.parse_episode_id(req.episode_id)
        ep_dirs = storage.ensure_episode_directories(season, episode)
        pq_file = ep_dirs["continuity"] / "continuity_ledger.parquet"
        if not pq_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No Continuity Ledger Parquet file found for {req.episode_id}",
            )

        ledger = ContinuityLedger.load_parquet(pq_file, episode_id=req.episode_id)
        invalidated = ledger.mutate_upstream_entry(
            scene_shot_id=req.scene_shot_id,
            added_physical_state=req.added_physical_state,
            updated_props=req.updated_props,
            added_reveal_flags=req.added_reveal_flags,
        )
        reconciled: List[str] = []
        if req.reconcile:
            reconciled = ledger.reconcile_state_graph()
        ledger.save_parquet(storage, season=season, episode=episode)

        return {
            "episode_id": req.episode_id,
            "mutated_shot_id": req.scene_shot_id,
            "invalidated_shots": invalidated,
            "reconciled_shots": reconciled,
            "entries": [e.model_dump() for e in ledger.entries],
        }

    @app.get("/files/{file_path:path}")
    def serve_studio_file(file_path: str) -> FileResponse:
        resolved = (storage.root_dir / file_path).resolve()
        if not str(resolved).startswith(str(storage.root_dir)) or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(str(resolved))

    return app
