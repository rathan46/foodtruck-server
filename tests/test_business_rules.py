from app.models.schemas import Coordinate
from app.services.offline_maps import cache_plan, nearby_map_fragments
from app.services.pricing import calculate_pricing, delivery_fee
from app.services.routing import assign_rider, micro_zone_id, zone_snapshot


def test_delivery_fee_steps_after_three_km():
    assert delivery_fee(3) == 30.0
    assert delivery_fee(3.1) == 40.0
    assert delivery_fee(5) == 50.0


def test_pricing_breakdown_includes_required_taxes_and_rider_earning():
    pricing = calculate_pricing(food_amount=650, distance_km=5)

    assert pricing.food_gst == 32.5
    assert pricing.delivery_fee == 50.0
    assert pricing.delivery_gst == 9.0
    assert pricing.platform_fee == 28.0
    assert pricing.platform_gst == 5.04
    assert pricing.total_payable == 774.54
    assert pricing.rider_earning == 50.14


def test_assignment_prefers_online_rider_in_expanding_radius():
    pickup = Coordinate(lat=12.9716, lng=77.5946)
    riders = [
        {
            "rider_id": "offline-close",
            "location": {"lat": 12.9717, "lng": 77.5947},
            "is_online": False,
            "rating": 5,
        },
        {
            "rider_id": "online-best",
            "location": {"lat": 12.9730, "lng": 77.5950},
            "is_online": True,
            "rating": 4.9,
            "completed_orders": 250,
            "average_delivery_minutes": 20,
        },
    ]

    assert assign_rider(riders, pickup)["rider_id"] == "online-best"


def test_micro_zone_snapshot_tracks_density():
    zone_id = micro_zone_id(Coordinate(lat=12.9716, lng=77.5946))
    snapshot = zone_snapshot(
        zone_id,
        restaurants=[{"location": {"lat": 12.9716, "lng": 77.5946}}],
        riders=[{"is_online": True, "current_zone_id": zone_id}],
        orders=[{"target_zone_id": zone_id, "status": "held"}],
    )

    assert snapshot["restaurant_clusters"] == 1
    assert snapshot["active_riders"] == 1
    assert snapshot["active_orders"] == 1
    assert snapshot["demand_heat"] == "balanced"


def test_offline_map_distribution_prioritizes_nearby_fragments():
    location = Coordinate(lat=12.9716, lng=77.5946)
    fragments = nearby_map_fragments(location, radius_km=20)
    plan = cache_plan(fragments, max_cache_mb=256)

    assert fragments
    assert all(fragment["distance_km"] <= 20 for fragment in fragments)
    assert any(fragment["priority"] == "active" for fragment in fragments)
    assert plan["strategy"] == "offline_first_hyperlocal"
    assert plan["routing_engine"] == "graphhopper-compatible"
    assert set(plan["preload_fragment_ids"]).issubset({fragment["fragment_id"] for fragment in fragments})
