from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import networkx as nx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from videostudio.storage import StudioStorage


class CharacterBible(BaseModel):
    """
    Persistent Identity Canon (Character Bible).
    Encapsulates unchanging baseline attributes: bone structure, facial geometry,
    facial proportions, eye shape and color, ethnic phenotype, baseline hair texture,
    and physical height, anchored by turnaround plates and LoRA weights.
    """

    character_id: str
    name: str
    bone_structure: str
    facial_geometry: str
    facial_proportions: str
    eye_shape_and_color: str
    ethnic_phenotype: str
    baseline_hair_texture: str
    physical_height: str
    turnaround_plates: Dict[str, str] = Field(
        default_factory=dict,
        description="Orthogonal turnaround sheets (front, angle_45, profile)",
    )
    lora_weights_uri: str = ""
    costume_variants: Dict[str, str] = Field(default_factory=dict)
    voice_profile: str = "neutral_cinematic"

    def invariant_digest(self) -> str:
        """Compute a deterministic SHA-256 digest of frozen biological identity invariants."""
        invariants = {
            "character_id": self.character_id,
            "bone_structure": self.bone_structure,
            "facial_geometry": self.facial_geometry,
            "facial_proportions": self.facial_proportions,
            "eye_shape_and_color": self.eye_shape_and_color,
            "ethnic_phenotype": self.ethnic_phenotype,
            "baseline_hair_texture": self.baseline_hair_texture,
            "physical_height": self.physical_height,
            "lora_weights_uri": self.lora_weights_uri,
        }
        raw = json.dumps(invariants, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def compose_invariant_anchor_prompt(self) -> str:
        """Extract frozen invariant traits for Dual-Bridge consistency conditioning."""
        return (
            f"[IDENTITY_ANCHOR:{self.character_id} | {self.name} | "
            f"BoneStructure: {self.bone_structure}; FacialGeometry: {self.facial_geometry}; "
            f"Eyes: {self.eye_shape_and_color}; Phenotype: {self.ethnic_phenotype}; "
            f"Hair: {self.baseline_hair_texture}; Height: {self.physical_height}]"
        )


class LocationBible(BaseModel):
    """Persistent Environment dossier stored under canon/bible/locations/."""

    location_id: str
    name: str
    spatial_coordinates: str
    architectural_prompt_card: str
    base_environment_render_uri: str
    default_lighting_setup: str = "Chiaroscuro"
    default_color_palette: str = "Cold cyan and amber"
    default_color_grade: str = "Teal & Orange"


class LoreNode(BaseModel):
    node_id: str
    entity_type: Literal["character", "location", "faction", "artifact", "lore_fact"]
    name: str
    biological_markers: Dict[str, str] = Field(default_factory=dict)
    allegiances: List[str] = Field(default_factory=list)
    current_physical_condition: str = "nominal"
    description: str = ""


class LoreEdge(BaseModel):
    source_id: str
    target_id: str
    relation: Literal[
        "POSSESSES",
        "ALLIED_WITH",
        "LOCATED_AT",
        "KNOWS_SECRET",
        "BETRAYED",
        "RESTRICTED_BY",
    ]
    valid_from_step: int = 0
    valid_to_step: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_active_at(self, step: int) -> bool:
        if step < self.valid_from_step:
            return False
        if self.valid_to_step is not None and step > self.valid_to_step:
            return False
        return True


def _tokenize(text: str) -> Counter[str]:
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return Counter(tokens)


def _cosine_similarity(vec_a: Counter[str], vec_b: Counter[str]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    intersection = set(vec_a.keys()) & set(vec_b.keys())
    numerator = sum(vec_a[k] * vec_b[k] for k in intersection)
    sum_a = sum(v * v for v in vec_a.values())
    sum_b = sum(v * v for v in vec_b.values())
    denom = math.sqrt(sum_a) * math.sqrt(sum_b)
    return numerator / denom if denom > 0 else 0.0


class LoreGraph:
    """
    Hybrid GraphRAG Knowledge Base combining a directed Property Graph (governed by
    temporal validity ranges) with a parallel vector similarity store for tonal precedents.
    """

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()
        self._nodes: Dict[str, LoreNode] = {}
        self._edges: List[LoreEdge] = []
        self._tonal_precedents: List[Dict[str, Any]] = []

    @property
    def nodes(self) -> Dict[str, LoreNode]:
        return self._nodes

    @property
    def edges(self) -> List[LoreEdge]:
        return self._edges

    def add_node(self, node: LoreNode) -> None:
        self._nodes[node.node_id] = node
        self._graph.add_node(node.node_id, **node.model_dump())

    def add_edge(self, edge: LoreEdge) -> None:
        self._edges.append(edge)
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            relation=edge.relation,
            valid_from_step=edge.valid_from_step,
            valid_to_step=edge.valid_to_step,
            metadata=edge.metadata,
        )

    def add_tonal_precedent(
        self, doc_id: str, text: str, tags: Optional[List[str]] = None
    ) -> None:
        self._tonal_precedents.append(
            {
                "doc_id": doc_id,
                "text": text,
                "tags": tags or [],
            }
        )

    def query_causal_constraints(
        self, character_id: str, current_step: int
    ) -> Dict[str, Any]:
        """
        Causal Value Engine: isolate active narrative constraints at `current_step`
        to determine which secrets a character knows, what artifacts they possess,
        active alliances, current location, and motive restrictions.
        """
        accessible_artifacts: List[str] = []
        known_secrets: List[str] = []
        active_alliances: List[str] = []
        current_locations: List[str] = []
        motive_restrictions: List[str] = []

        for edge in self._edges:
            if edge.source_id != character_id or not edge.is_active_at(current_step):
                continue
            if edge.relation == "POSSESSES":
                accessible_artifacts.append(edge.target_id)
            elif edge.relation == "KNOWS_SECRET":
                known_secrets.append(edge.target_id)
            elif edge.relation == "ALLIED_WITH":
                active_alliances.append(edge.target_id)
            elif edge.relation == "LOCATED_AT":
                current_locations.append(edge.target_id)
            elif edge.relation == "RESTRICTED_BY":
                motive_restrictions.append(edge.target_id)

        node = self._nodes.get(character_id)
        return {
            "character_id": character_id,
            "step": current_step,
            "physical_condition": node.current_physical_condition if node else "unknown",
            "accessible_artifacts": accessible_artifacts,
            "known_secrets": known_secrets,
            "active_alliances": active_alliances,
            "current_locations": current_locations,
            "motive_restrictions": motive_restrictions,
        }

    def retrieve_tonal_precedents(
        self, query: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Retrieve tonal precedents and stylistic motifs via cosine similarity."""
        q_vec = _tokenize(query)
        scored: List[tuple[float, Dict[str, Any]]] = []
        for item in self._tonal_precedents:
            doc_vec = _tokenize(item["text"] + " " + " ".join(item.get("tags", [])))
            score = _cosine_similarity(q_vec, doc_vec)
            scored.append((score, {**item, "similarity_score": round(score, 4)}))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.model_dump() for n in self._nodes.values()],
            "edges": [e.model_dump() for e in self._edges],
            "tonal_precedents": self._tonal_precedents,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoreGraph":
        graph = cls()
        for n in data.get("nodes", []):
            graph.add_node(LoreNode.model_validate(n))
        for e in data.get("edges", []):
            graph.add_edge(LoreEdge.model_validate(e))
        for tp in data.get("tonal_precedents", []):
            graph.add_tonal_precedent(
                doc_id=tp["doc_id"],
                text=tp["text"],
                tags=tp.get("tags", []),
            )
        return graph

    def to_neo4j_cypher(self) -> str:
        """Export the property graph to deterministic Neo4j Cypher statements."""
        lines: List[str] = ["// VideoStudio GraphRAG Property Graph Dump"]
        for node in self._nodes.values():
            label = "".join(part.capitalize() for part in node.entity_type.split("_"))
            safe_name = node.name.replace("'", "\\'")
            safe_desc = node.description.replace("'", "\\'")
            lines.append(
                f"MERGE (n:{label} {{id: '{node.node_id}'}}) "
                f"SET n.name = '{safe_name}', n.condition = '{node.current_physical_condition}', "
                f"n.description = '{safe_desc}';"
            )
        for edge in self._edges:
            to_step = "null" if edge.valid_to_step is None else str(edge.valid_to_step)
            lines.append(
                f"MATCH (a {{id: '{edge.source_id}'}}), (b {{id: '{edge.target_id}'}}) "
                f"MERGE (a)-[r:{edge.relation} {{valid_from: {edge.valid_from_step}, valid_to: {to_step}}}]->(b);"
            )
        return "\n".join(lines) + "\n"


def seed_default_canon(storage: "StudioStorage") -> LoreGraph:
    """
    Populate canonical Character Bibles, Location Bibles, and the GraphRAG Lore Graph
    so the studio has rich, production-grade assets ready out of the box.
    """
    elena = CharacterBible(
        character_id="CHAR_ELENA_VANCE",
        name="Commander Elena Vance",
        bone_structure="High zygomatic arches, defined mandibular angle",
        facial_geometry="Oval-rectangular face, faint 12mm scar over left brow",
        facial_proportions="Balanced facial thirds, intercanthal distance 32mm",
        eye_shape_and_color="Almond-shaped slate-grey eyes with amber limbal ring",
        ethnic_phenotype="Northern Mediterranean / Nordic mix, olive-fair complexion",
        baseline_hair_texture="Coarse dark auburn hair braided tightly at nape",
        physical_height="176cm",
        turnaround_plates={
            "front": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_front.png",
            "angle_45": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_45.png",
            "profile": "canon/bible/characters/CHAR_ELENA_VANCE/turnaround_profile.png",
        },
        lora_weights_uri="canon/bible/characters/CHAR_ELENA_VANCE/elena_vance_v1.safetensors",
        costume_variants={
            "WARD_ELENA_EVA_TRENCH": "Weathered navy pressure-trench with brass collar seals",
            "WARD_ELENA_FLIGHT_DECK": "Charcoal utility jumpsuit with Helios Watch patch",
        },
        voice_profile="contralto_measured_urgent",
    )

    koren = CharacterBible(
        character_id="CHAR_MARCUS_KOREN",
        name="Dr. Marcus Koren",
        bone_structure="Angular temporal bone, narrow nasal bridge, prominent chin",
        facial_geometry="Long diamond face, deep nasolabial folds",
        facial_proportions="Slightly elongated middle third, narrow-set eyes",
        eye_shape_and_color="Deep-set hazel-green eyes behind rimless titanium spectacles",
        ethnic_phenotype="Central European complexion with silver-streaked beard",
        baseline_hair_texture="Fine iron-grey hair swept back from temples",
        physical_height="183cm",
        turnaround_plates={
            "front": "canon/bible/characters/CHAR_MARCUS_KOREN/turnaround_front.png",
            "angle_45": "canon/bible/characters/CHAR_MARCUS_KOREN/turnaround_45.png",
            "profile": "canon/bible/characters/CHAR_MARCUS_KOREN/turnaround_profile.png",
        },
        lora_weights_uri="canon/bible/characters/CHAR_MARCUS_KOREN/marcus_koren_v1.safetensors",
        costume_variants={
            "WARD_KOREN_LAB_PARKA": "Thermal graphite lab coat with copper dosimeter badge",
            "WARD_KOREN_HAZMAT": "Amber-visored atmospheric excursion suit",
        },
        voice_profile="baritone_resonant_guarded",
    )

    storage.save_character_bible(elena)
    storage.save_character_bible(koren)

    dome = LocationBible(
        location_id="LOC_OBSERVATORY_DOME",
        name="Helios Deep-Space Observatory Dome",
        spatial_coordinates="LAT +64.12 LON -21.89 ALT 2400M",
        architectural_prompt_card=(
            "Brutalist concrete and brass circular observatory dome, central equatorial telescope mount, "
            "condensation on curved steel ribs, glowing CRT azimuth consoles"
        ),
        base_environment_render_uri="canon/bible/locations/LOC_OBSERVATORY_DOME/base_render.png",
        default_lighting_setup="Chiaroscuro",
        default_color_palette="Cold cyan and amber instrument glow",
        default_color_grade="Teal & Orange",
    )

    vault = LocationBible(
        location_id="LOC_SUBLEVEL_RELAY_VAULT",
        name="Sub-Level 4 Cryogenic Relay Vault",
        spatial_coordinates="LAT +64.12 LON -21.89 DEPTH -180M",
        architectural_prompt_card=(
            "Subterranean basalt corridor lined with frost-covered waveguide conduits, "
            "heavy interlocking pressure doors, amber emergency beacons"
        ),
        base_environment_render_uri="canon/bible/locations/LOC_SUBLEVEL_RELAY_VAULT/base_render.png",
        default_lighting_setup="Volumetric Split",
        default_color_palette="Steel blue and sodium vapor orange",
        default_color_grade="Bleach Bypass",
    )

    storage.save_location_bible(dome)
    storage.save_location_bible(vault)

    graph = LoreGraph()
    graph.add_node(
        LoreNode(
            node_id="CHAR_ELENA_VANCE",
            entity_type="character",
            name="Commander Elena Vance",
            biological_markers={"scar": "left_brow_12mm", "eyes": "slate_grey"},
            allegiances=["FACTION_HELIOS_WATCH"],
            current_physical_condition="nominal",
            description="Commander of the Helios Observatory guarding the deep-space telemetry array.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="CHAR_MARCUS_KOREN",
            entity_type="character",
            name="Dr. Marcus Koren",
            biological_markers={"glasses": "rimless_titanium", "beard": "silver_streaked"},
            allegiances=["FACTION_HELIOS_WATCH", "FACTION_AETHER_DIRECTORATE"],
            current_physical_condition="nominal",
            description="Chief astrophysicist secretly archiving unauthorized orbital transmissions.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="LOC_OBSERVATORY_DOME",
            entity_type="location",
            name="Helios Deep-Space Observatory Dome",
            description="Primary astrometric tracking dome battered by sub-polar storms.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="LOC_SUBLEVEL_RELAY_VAULT",
            entity_type="location",
            name="Sub-Level 4 Cryogenic Relay Vault",
            description="Deep subterranean vault housing the quantum phase-lock cores.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="ART_CHRONO_COMPASS",
            entity_type="artifact",
            name="Brass Chrono-Compass",
            description="Mechanical decryption key required to unseal the Sub-Level 4 vault.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="SECRET_GHOST_TELEMETRY",
            entity_type="lore_fact",
            name="The Ghost Telemetry Carrier Wave",
            description="Decommissioned Beacon 9 is still broadcasting coordinates from beyond the Jovian shadow.",
        )
    )

    graph.add_edge(
        LoreEdge(
            source_id="CHAR_ELENA_VANCE",
            target_id="ART_CHRONO_COMPASS",
            relation="POSSESSES",
            valid_from_step=0,
            valid_to_step=None,
            metadata={"affordance": "clipped_to_belt"},
        )
    )
    graph.add_edge(
        LoreEdge(
            source_id="CHAR_ELENA_VANCE",
            target_id="LOC_OBSERVATORY_DOME",
            relation="LOCATED_AT",
            valid_from_step=0,
            valid_to_step=2,
        )
    )
    graph.add_edge(
        LoreEdge(
            source_id="CHAR_MARCUS_KOREN",
            target_id="SECRET_GHOST_TELEMETRY",
            relation="KNOWS_SECRET",
            valid_from_step=0,
            valid_to_step=None,
        )
    )
    graph.add_edge(
        LoreEdge(
            source_id="CHAR_ELENA_VANCE",
            target_id="SECRET_GHOST_TELEMETRY",
            relation="KNOWS_SECRET",
            valid_from_step=2,
            valid_to_step=None,
        )
    )

    graph.add_tonal_precedent(
        doc_id="PRECEDENT_CHIAROSCURO_SCI_FI",
        text="Tactile analog-futurist sci-fi tension: brass dials, rain-streaked glass, chiaroscuro instrument lighting, clipped dialogue heavy with subtext.",
        tags=["analog-futurism", "chiaroscuro", "tension", "observatory"],
    )
    graph.add_tonal_precedent(
        doc_id="PRECEDENT_SUBLEVEL_DESCENT",
        text="Claustrophobic subterranean industrial descent: venting cryo-steam, bleach-bypass sodium lighting, footsteps echoing on grated catwalks.",
        tags=["vault", "bleach-bypass", "industrial", "suspense"],
    )

    storage.save_lore_graph(graph)
    return graph
