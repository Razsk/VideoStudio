from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from videostudio.lore import CharacterBible, LocationBible, LoreGraph


class StudioStorage:
    """
    Deterministic, content-addressed storage repository managing canonical series lore
    and episodic execution instances according to the Architectural Blueprint.
    """

    def __init__(self, root_dir: Path | str = ".") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.ensure_canon_directories()

    @property
    def characters_dir(self) -> Path:
        return self.root_dir / "canon" / "bible" / "characters"

    @property
    def locations_dir(self) -> Path:
        return self.root_dir / "canon" / "bible" / "locations"

    @property
    def lore_graph_dir(self) -> Path:
        return self.root_dir / "canon" / "lore_graph"

    def ensure_canon_directories(self) -> Dict[str, Path]:
        dirs = {
            "characters": self.characters_dir,
            "locations": self.locations_dir,
            "lore_graph": self.lore_graph_dir,
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    def episode_root(self, season: int, episode: int) -> Path:
        return self.root_dir / f"season_{season:02d}" / f"episode_{episode:02d}"

    def ensure_episode_directories(self, season: int, episode: int) -> Dict[str, Path]:
        ep_root = self.episode_root(season, episode)
        subdirs = {
            "script": ep_root / "script",
            "continuity": ep_root / "continuity",
            "storyboards": ep_root / "storyboards",
            "media": ep_root / "media",
            "editorial": ep_root / "editorial",
        }
        for d in subdirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return subdirs

    @staticmethod
    def parse_episode_id(episode_id: str) -> tuple[int, int]:
        """Parse 'S01E02' or 'season_01_episode_02' into (1, 2)."""
        cleaned = episode_id.upper().strip()
        if cleaned.startswith("S") and "E" in cleaned:
            parts = cleaned[1:].split("E", 1)
            return int(parts[0]), int(parts[1])
        return 1, 1

    @staticmethod
    def content_sha256(data: bytes | str) -> str:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        return hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Canonical Bible & Lore Graph Persistence
    # ------------------------------------------------------------------

    def save_character_bible(self, bible: "CharacterBible") -> Path:
        char_dir = self.characters_dir / bible.character_id
        char_dir.mkdir(parents=True, exist_ok=True)
        target = char_dir / "character_bible.json"
        payload = bible.model_dump()
        payload["invariant_sha256"] = bible.invariant_digest()
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def load_character_bible(self, character_id: str) -> "CharacterBible":
        from videostudio.lore import CharacterBible

        target = self.characters_dir / character_id / "character_bible.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        data.pop("invariant_sha256", None)
        return CharacterBible.model_validate(data)

    def list_character_bibles(self) -> List["CharacterBible"]:
        from videostudio.lore import CharacterBible

        results: List[CharacterBible] = []
        if not self.characters_dir.exists():
            return results
        for p in sorted(self.characters_dir.glob("*/character_bible.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            data.pop("invariant_sha256", None)
            results.append(CharacterBible.model_validate(data))
        return results

    def save_location_bible(self, location: "LocationBible") -> Path:
        loc_dir = self.locations_dir / location.location_id
        loc_dir.mkdir(parents=True, exist_ok=True)
        target = loc_dir / "location_bible.json"
        target.write_text(json.dumps(location.model_dump(), indent=2), encoding="utf-8")
        return target

    def load_location_bible(self, location_id: str) -> "LocationBible":
        from videostudio.lore import LocationBible

        target = self.locations_dir / location_id / "location_bible.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        return LocationBible.model_validate(data)

    def list_location_bibles(self) -> List["LocationBible"]:
        from videostudio.lore import LocationBible

        results: List[LocationBible] = []
        if not self.locations_dir.exists():
            return results
        for p in sorted(self.locations_dir.glob("*/location_bible.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            results.append(LocationBible.model_validate(data))
        return results

    def save_lore_graph(self, graph: "LoreGraph") -> tuple[Path, Path]:
        json_path = self.lore_graph_dir / "property_graph.json"
        cypher_path = self.lore_graph_dir / "neo4j_dump.cypher"
        json_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        cypher_path.write_text(graph.to_neo4j_cypher(), encoding="utf-8")
        return json_path, cypher_path

    def load_lore_graph(self) -> "LoreGraph":
        from videostudio.lore import LoreGraph

        json_path = self.lore_graph_dir / "property_graph.json"
        if not json_path.exists():
            return LoreGraph()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return LoreGraph.from_dict(data)
