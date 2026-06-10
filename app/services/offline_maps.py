from __future__ import annotations

import math
from typing import Dict, Iterable, List

from app.models.schemas import Coordinate
from app.services.routing import as_coordinate, haversine_km, micro_zone_id


DEFAULT_FRAGMENT_RADIUS_KM = 20.0
FRAGMENT_CELL_SIZE = 0.1
INDIA_BOUNDS = {
    "min_lat": 6.5,
    "max_lat": 37.5,
    "min_lng": 68.0,
    "max_lng": 97.5,
}


def osm_fragment_id(point: Coordinate, cell_size: float = FRAGMENT_CELL_SIZE) -> str:
    point = as_coordinate(point)
    lat_bucket = math.floor(point.lat / cell_size)
    lng_bucket = math.floor(point.lng / cell_size)
    return f"IN-OSM-{lat_bucket}-{lng_bucket}"


def fragment_center(fragment_id: str, cell_size: float = FRAGMENT_CELL_SIZE) -> Coordinate:
    _, _, lat_bucket, lng_bucket = fragment_id.split("-")
    return Coordinate(
        lat=(int(lat_bucket) + 0.5) * cell_size,
        lng=(int(lng_bucket) + 0.5) * cell_size,
    )


def is_inside_india_bounds(point: Coordinate) -> bool:
    point = as_coordinate(point)
    return (
        INDIA_BOUNDS["min_lat"] <= point.lat <= INDIA_BOUNDS["max_lat"]
        and INDIA_BOUNDS["min_lng"] <= point.lng <= INDIA_BOUNDS["max_lng"]
    )


def nearby_map_fragments(
    location: Coordinate,
    radius_km: float = DEFAULT_FRAGMENT_RADIUS_KM,
    active_zones: Iterable[Dict] = (),
) -> List[Dict]:
    location = as_coordinate(location)
    lat_step = FRAGMENT_CELL_SIZE
    lng_step = FRAGMENT_CELL_SIZE
    lat_window = max(1, math.ceil(radius_km / 111.0 / lat_step))
    lng_window = max(1, math.ceil(radius_km / (111.0 * max(math.cos(math.radians(location.lat)), 0.2)) / lng_step))
    center_lat_bucket = math.floor(location.lat / lat_step)
    center_lng_bucket = math.floor(location.lng / lng_step)
    current_fragment_id = osm_fragment_id(location)
    fragments: List[Dict] = []

    for lat_bucket in range(center_lat_bucket - lat_window, center_lat_bucket + lat_window + 1):
        for lng_bucket in range(center_lng_bucket - lng_window, center_lng_bucket + lng_window + 1):
            center = Coordinate(lat=(lat_bucket + 0.5) * lat_step, lng=(lng_bucket + 0.5) * lng_step)
            if not is_inside_india_bounds(center):
                continue
            distance = haversine_km(location, center)
            if distance <= radius_km:
                fragment_id = f"IN-OSM-{lat_bucket}-{lng_bucket}"
                fragment = fragment_manifest(fragment_id, center, distance, active_zones)
                if fragment_id == current_fragment_id:
                    fragment["priority"] = "active"
                    fragment["max_cache_hours"] = 72
                    fragment["approx_size_mb"] = 18
                fragments.append(fragment)

    return sorted(fragments, key=lambda fragment: (fragment["priority"], fragment["distance_km"]))


def fragment_manifest(fragment_id: str, center: Coordinate, distance_km: float, active_zones: Iterable[Dict]) -> Dict:
    zone_id = micro_zone_id(center)
    zone_hot = any(zone.get("id") == zone_id or micro_zone_id(zone["center"]) == zone_id for zone in active_zones)
    priority = "active" if distance_km <= 5 or zone_hot else "preload" if distance_km <= 14 else "standby"
    return {
        "fragment_id": fragment_id,
        "zone_id": zone_id,
        "center": center.model_dump(),
        "distance_km": round(distance_km, 2),
        "priority": priority,
        "tile_url": f"/api/maps/fragments/{fragment_id}/tiles/{{z}}/{{x}}/{{y}}.pbf",
        "routing_graph_url": f"/api/maps/fragments/{fragment_id}/graph",
        "etag": f"{fragment_id}-v1",
        "approx_size_mb": 18 if priority == "active" else 12,
        "max_cache_hours": 72 if priority == "active" else 24,
    }


def cache_plan(fragments: List[Dict], max_cache_mb: int = 512) -> Dict:
    active = [fragment for fragment in fragments if fragment["priority"] == "active"]
    preload = [fragment for fragment in fragments if fragment["priority"] == "preload"]
    standby = [fragment for fragment in fragments if fragment["priority"] == "standby"]
    keep = active + preload[:12]
    used_mb = sum(fragment["approx_size_mb"] for fragment in keep)
    while used_mb > max_cache_mb and preload:
        preload.pop()
        keep = active + preload[:12]
        used_mb = sum(fragment["approx_size_mb"] for fragment in keep)
    return {
        "strategy": "offline_first_hyperlocal",
        "max_cache_mb": max_cache_mb,
        "keep_fragment_ids": [fragment["fragment_id"] for fragment in keep],
        "evict_priorities": ["expired", "outside_20km", "least_recently_used", "standby"],
        "preload_fragment_ids": [fragment["fragment_id"] for fragment in preload[:6]],
        "used_mb": used_mb,
        "routing_engine": "graphhopper-compatible",
    }
