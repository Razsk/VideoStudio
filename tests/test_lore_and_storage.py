from pathlib import Path

from videostudio.lore import (
    CharacterBible,
    LocationBible,
    LoreEdge,
    LoreGraph,
    LoreNode,
    seed_default_canon,
)
from videostudio.storage import StudioStorage


def test_studio_storage_creates_canonical_and_episodic_hierarchy(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    ep_paths = storage.ensure_episode_directories(season=1, episode=2)

    assert (tmp_path / "canon" / "bible" / "characters").is_dir()
    assert (tmp_path / "canon" / "bible" / "locations").is_dir()
    assert (tmp_path / "canon" / "lore_graph").is_dir()
    assert ep_paths["script"] == tmp_path / "season_01" / "episode_02" / "script"
    assert ep_paths["continuity"] == tmp_path / "season_01" / "episode_02" / "continuity"
    assert ep_paths["storyboards"] == tmp_path / "season_01" / "episode_02" / "storyboards"
    assert ep_paths["media"] == tmp_path / "season_01" / "episode_02" / "media"
    assert ep_paths["editorial"] == tmp_path / "season_01" / "episode_02" / "editorial"
    assert all(p.is_dir() for p in ep_paths.values())


def test_character_bible_invariants_and_content_hash(tmp_path: Path):
    storage = StudioStorage(root_dir=tmp_path)
    char = CharacterBible(
        character_id="CHAR_ELENA_VANCE",
        name="Commander Elena Vance",
        bone_structure="High zygomatic arches, defined mandibular angle",
        facial_geometry="Oval-rectangular face, slight asymmetry on left brow",
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
            "WARD_ELENA_FLIGHT_DECK": "Charcoal utility jumpsuit with mission patch",
        },
    )
    saved_path = storage.save_character_bible(char)
    assert saved_path.exists()

    loaded = storage.load_character_bible("CHAR_ELENA_VANCE")
    assert loaded.character_id == "CHAR_ELENA_VANCE"
    assert loaded.invariant_digest() == char.invariant_digest()
    assert "Almond-shaped slate-grey eyes" in loaded.compose_invariant_anchor_prompt()


def test_graphrag_temporal_validity_and_causal_constraints(tmp_path: Path):
    graph = LoreGraph()
    graph.add_node(
        LoreNode(
            node_id="CHAR_ELENA_VANCE",
            entity_type="character",
            name="Elena Vance",
            biological_markers={"eye_color": "slate-grey", "scar": "left_brow"},
            allegiances=["FACTION_HELIOS_WATCH"],
            current_physical_condition="uninjured",
            description="Chief telemetry officer stationed at the Europa Observatory Dome.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="ART_CHRONO_COMPASS",
            entity_type="artifact",
            name="Chrono-Compass",
            description="Brass astrometric relay key capable of unlocking orbital beacon archives.",
        )
    )
    graph.add_node(
        LoreNode(
            node_id="SECRET_ORBITAL_SABOTAGE",
            entity_type="lore_fact",
            name="Orbital Array Sabotage",
            description="The telemetry blackout was deliberately triggered from inside Sector 4.",
        )
    )

    # Elena possesses the compass only from step 1 to step 3 (loses it at step 4)
    graph.add_edge(
        LoreEdge(
            source_id="CHAR_ELENA_VANCE",
            target_id="ART_CHRONO_COMPASS",
            relation="POSSESSES",
            valid_from_step=1,
            valid_to_step=3,
            metadata={"affordance": "locked_in_satchel"},
        )
    )
    # Elena learns the sabotage secret only starting at step 3
    graph.add_edge(
        LoreEdge(
            source_id="CHAR_ELENA_VANCE",
            target_id="SECRET_ORBITAL_SABOTAGE",
            relation="KNOWS_SECRET",
            valid_from_step=3,
            valid_to_step=None,
        )
    )
    graph.add_tonal_precedent(
        doc_id="TONE_01",
        text="Claustrophobic hard sci-fi thriller with tactile brass instruments, cold rain, and chiaroscuro shadows.",
        tags=["thriller", "sci-fi", "observatory"],
    )

    # At step 2: possesses compass, does NOT know secret
    constraints_step_2 = graph.query_causal_constraints("CHAR_ELENA_VANCE", current_step=2)
    assert "ART_CHRONO_COMPASS" in constraints_step_2["accessible_artifacts"]
    assert "SECRET_ORBITAL_SABOTAGE" not in constraints_step_2["known_secrets"]

    # At step 4: no longer possesses compass, DOES know secret
    constraints_step_4 = graph.query_causal_constraints("CHAR_ELENA_VANCE", current_step=4)
    assert "ART_CHRONO_COMPASS" not in constraints_step_4["accessible_artifacts"]
    assert "SECRET_ORBITAL_SABOTAGE" in constraints_step_4["known_secrets"]

    # Vector retrieval for tonal precedents
    precedents = graph.retrieve_tonal_precedents("brass instruments in a claustrophobic observatory", top_k=1)
    assert len(precedents) == 1
    assert precedents[0]["doc_id"] == "TONE_01"

    # Persistence and Neo4j Cypher export
    storage = StudioStorage(root_dir=tmp_path)
    seed_default_canon(storage)
    loaded_graph = storage.load_lore_graph()
    cypher = loaded_graph.to_neo4j_cypher()
    assert "MERGE (n:Character {id: 'CHAR_ELENA_VANCE'})" in cypher
