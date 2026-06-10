from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional


class MBTilesStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def is_ready(self) -> bool:
        return self.path.exists() and self.path.is_file()

    def metadata(self) -> Dict[str, str]:
        if not self.is_ready():
            return {}
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("SELECT name, value FROM metadata").fetchall()
        return {str(name): str(value) for name, value in rows}

    def tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        if not self.is_ready():
            return None
        flipped_y = (1 << z) - 1 - y
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT tile_data
                FROM tiles
                WHERE zoom_level = ? AND tile_column = ? AND tile_row IN (?, ?)
                LIMIT 1
                """,
                (z, x, flipped_y, y),
            ).fetchone()
        return bytes(row[0]) if row else None

    def tilejson(self, base_url: str) -> Dict:
        metadata = self.metadata()
        bounds = [float(value) for value in metadata.get("bounds", "68.0,6.5,97.5,37.5").split(",")]
        vector_layers = []
        if metadata.get("json"):
            try:
                vector_layers = json.loads(metadata["json"]).get("vector_layers", [])
            except json.JSONDecodeError:
                vector_layers = []
        return {
            "tilejson": "3.0.0",
            "name": metadata.get("name", "FOODTRUCK India OSM Vector Tiles"),
            "version": metadata.get("version", "1.0"),
            "scheme": metadata.get("scheme", "xyz"),
            "tiles": [f"{base_url}/api/maps/tiles/{{z}}/{{x}}/{{y}}.pbf"],
            "minzoom": int(metadata.get("minzoom", 0)),
            "maxzoom": int(metadata.get("maxzoom", 14)),
            "bounds": bounds,
            "attribution": metadata.get("attribution", "(c) OpenStreetMap contributors"),
            "vector_layers": vector_layers,
        }
