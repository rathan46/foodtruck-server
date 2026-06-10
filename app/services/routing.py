import math
from typing import Dict, Iterable, List

from app.models.schemas import Coordinate


def as_coordinate(value: Coordinate | Dict) -> Coordinate:
    return value if isinstance(value, Coordinate) else Coordinate(**value)


def haversine_km(a: Coordinate, b: Coordinate) -> float:
    a = as_coordinate(a)
    b = as_coordinate(b)
    radius = 6371.0
    d_lat = math.radians(b.lat - a.lat)
    d_lng = math.radians(b.lng - a.lng)
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def score_rider(rider: Dict, pickup: Coordinate) -> float:
    pickup = as_coordinate(pickup)
    distance = haversine_km(rider["location"], pickup)
    rating = float(rider.get("rating", 4.5))
    completed = min(int(rider.get("completed_orders", 0)), 500) / 500
    speed_penalty = float(rider.get("average_delivery_minutes", 30)) / 60
    active_load_penalty = float(rider.get("active_load", 0)) * 1.8
    idle_bonus = min(float(rider.get("idle_minutes", 0)), 20) / 20
    return distance * 3 - rating - completed + speed_penalty + active_load_penalty - idle_bonus


def bearing_degrees(a: Coordinate, b: Coordinate) -> float:
    a = as_coordinate(a)
    b = as_coordinate(b)
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    d_lng = math.radians(b.lng - a.lng)
    y = math.sin(d_lng) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lng)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def heading_delta(a: float, b: float) -> float:
    delta = abs(a - b) % 360
    return min(delta, 360 - delta)


def logistics_score(rider: Dict, pickup: Coordinate, drop: Coordinate | None = None) -> Dict:
    pickup = as_coordinate(pickup)
    distance = haversine_km(rider["location"], pickup)
    base = score_rider(rider, pickup)
    momentum_penalty = 0.0
    if drop:
        desired = bearing_degrees(pickup, drop)
        momentum_penalty = heading_delta(float(rider.get("heading_degrees", 0)), desired) / 90
    batching_bonus = 0.8 if 0 < int(rider.get("active_load", 0)) < 3 else 0.0
    score = round(base + momentum_penalty - batching_bonus, 3)
    return {
        "rider": rider,
        "distance_km": round(distance, 3),
        "score": score,
        "momentum_penalty": round(momentum_penalty, 3),
        "batching_bonus": batching_bonus,
    }


def assign_rider(riders: Iterable[Dict], pickup: Coordinate, drop: Coordinate | None = None) -> Dict | None:
    pickup = as_coordinate(pickup)
    online = [r for r in riders if r.get("is_online")]
    for radius in [0.5, 1, 2, 5, 10]:
        candidates: List[Dict] = [
            logistics_score(rider, pickup, drop)
            for rider in online
            if haversine_km(rider["location"], pickup) <= radius
        ]
        if candidates:
            return sorted(candidates, key=lambda candidate: candidate["score"])[0]["rider"]
    return None


def micro_zone_id(point: Coordinate, cell_size: float = 0.02) -> str:
    point = as_coordinate(point)
    return f"Z{math.floor(point.lat / cell_size)}-{math.floor(point.lng / cell_size)}"


def zone_snapshot(zone_id: str, restaurants: Iterable[Dict], riders: Iterable[Dict], orders: Iterable[Dict]) -> Dict:
    active_riders = [r for r in riders if r.get("is_online") and r.get("current_zone_id") == zone_id]
    active_orders = [o for o in orders if o.get("target_zone_id") == zone_id and o.get("status") in {"held", "created", "accepted", "preparing"}]
    restaurant_cluster = [r for r in restaurants if micro_zone_id(r["location"]) == zone_id]
    density = len(active_orders) / max(len(active_riders), 1)
    return {
        "zone_id": zone_id,
        "restaurant_clusters": len(restaurant_cluster),
        "active_riders": len(active_riders),
        "active_orders": len(active_orders),
        "delivery_density": round(density, 2),
        "demand_heat": "high" if density >= 2 else "balanced" if density >= 1 else "light",
    }
