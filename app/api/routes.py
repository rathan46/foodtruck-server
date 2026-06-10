from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.schemas import (
    AddressIn,
    AnalyticsOut,
    DispatchPlanIn,
    MapFragmentRequestIn,
    MenuItemIn,
    OfferIn,
    OrderIn,
    OrderStatusIn,
    OTPRequestIn,
    OTPVerifyIn,
    PricingIn,
    RestaurantIn,
    RestaurantStatusIn,
    RiderLocationIn,
    TokenOut,
    ZoneIn,
)
from app.services.otp import otp_service
from app.services.offline_maps import cache_plan, fragment_center, fragment_manifest, nearby_map_fragments, osm_fragment_id
from app.services.map_tiles import MBTilesStore
from app.services.pricing import calculate_pricing
from app.services.realtime import manager
from app.services.routing import assign_rider, micro_zone_id, zone_snapshot

router = APIRouter()

restaurants: Dict[str, dict] = {}
menu_items: Dict[str, dict] = {}
riders: Dict[str, dict] = {}
orders: Dict[str, dict] = {}
addresses: Dict[str, List[dict]] = {}
zones: Dict[str, dict] = {}


def tile_store() -> MBTilesStore:
    return MBTilesStore(get_settings().vector_mbtiles)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "FOODTRUCK"}


@router.post("/auth/request-otp")
async def request_otp(payload: OTPRequestIn) -> dict:
    return await otp_service.create_request(payload.mobile, payload.role.value)


@router.post("/auth/verify-otp", response_model=TokenOut)
async def verify_otp(payload: OTPVerifyIn) -> TokenOut:
    if not otp_service.verify(payload.mobile, payload.role.value, payload.otp):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")
    token = create_access_token(subject=payload.mobile, role=payload.role.value)
    return TokenOut(access_token=token, role=payload.role)


@router.get("/otp/dashboard")
async def otp_dashboard(client_token: str = Header(default="")) -> dict:
    if client_token != get_settings().otp_client_token:
        raise HTTPException(status_code=403, detail="OTP sender not authorized")
    return otp_service.dashboard()


@router.websocket("/ws/otp-sender")
async def otp_sender_socket(websocket: WebSocket, client_token: str = "") -> None:
    if client_token != get_settings().otp_client_token:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    try:
        while True:
            payload = await otp_service.next_request()
            await websocket.send_json(payload)
            result = await websocket.receive_json()
            if result.get("status") == "sent":
                otp_service.mark_sent(payload)
            else:
                otp_service.mark_failed({**payload, "error": str(result.get("error", "unknown"))})
    except WebSocketDisconnect:
        return


@router.post("/restaurants")
async def create_restaurant(payload: RestaurantIn) -> dict:
    restaurant_id = str(uuid4())
    restaurants[restaurant_id] = {
        "id": restaurant_id,
        **payload.model_dump(),
        "rating": 4.7,
        "offers": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return restaurants[restaurant_id]


@router.get("/restaurants/nearby")
async def nearby_restaurants() -> List[dict]:
    open_restaurants = [restaurant for restaurant in restaurants.values() if restaurant["is_open"]]
    return sorted(open_restaurants, key=restaurant_efficiency_score, reverse=True)


def restaurant_efficiency_score(restaurant: dict) -> float:
    zone_id = micro_zone_id(restaurant["location"])
    riders_in_zone = len([r for r in riders.values() if r.get("is_online") and r.get("current_zone_id") == zone_id])
    active_load = len([
        order for order in orders.values()
        if order["restaurant_id"] == restaurant["id"] and order["status"] in {"held", "created", "accepted", "preparing"}
    ])
    prep_speed = float(restaurant.get("prep_speed_index", 1.0))
    rating = float(restaurant.get("rating", 4.5))
    return round(riders_in_zone * 2 + prep_speed + rating - active_load * 1.4, 3)


@router.patch("/restaurants/{restaurant_id}/status")
async def update_restaurant_status(restaurant_id: str, payload: RestaurantStatusIn) -> dict:
    restaurant = restaurants.get(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant["is_open"] = payload.is_open
    await manager.broadcast("restaurants", {"type": "restaurant_status", "payload": restaurant})
    return restaurant


@router.post("/restaurants/offers")
async def create_offer(payload: OfferIn) -> dict:
    restaurant = restaurants.get(payload.restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    offer = {"id": str(uuid4()), **payload.model_dump()}
    restaurant["offers"].insert(0, offer)
    return offer


@router.post("/restaurants/menu")
async def add_menu_item(payload: MenuItemIn) -> dict:
    if payload.restaurant_id not in restaurants:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    item_id = str(uuid4())
    menu_items[item_id] = {"id": item_id, **payload.model_dump()}
    return menu_items[item_id]


@router.get("/restaurants/{restaurant_id}/menu")
async def get_menu(restaurant_id: str) -> List[dict]:
    return [item for item in menu_items.values() if item["restaurant_id"] == restaurant_id]


@router.post("/customers/addresses")
async def save_address(payload: AddressIn) -> dict:
    address = {"id": str(uuid4()), **payload.model_dump()}
    bucket = addresses.setdefault(payload.customer_mobile, [])
    bucket[:] = [item for item in bucket if item["label"] != payload.label]
    bucket.insert(0, address)
    return address


@router.get("/customers/{mobile}/addresses")
async def customer_addresses(mobile: str) -> List[dict]:
    return addresses.get(mobile, [])


@router.post("/pricing")
async def pricing(payload: PricingIn):
    return calculate_pricing(
        payload.food_amount,
        payload.distance_km,
        payload.traffic_multiplier,
        payload.rider_availability_index,
        payload.batching_discount,
    )


@router.post("/riders/location")
async def rider_location(payload: RiderLocationIn) -> dict:
    rider = payload.model_dump()
    rider["current_zone_id"] = rider.get("current_zone_id") or micro_zone_id(payload.location)
    riders[payload.rider_id] = rider
    await manager.broadcast("riders", {"type": "rider_location", "payload": riders[payload.rider_id]})
    return {"status": "updated"}


@router.post("/zones")
async def create_zone(payload: ZoneIn) -> dict:
    zone_id = micro_zone_id(payload.center)
    zones[zone_id] = {"id": zone_id, **payload.model_dump()}
    return zones[zone_id]


@router.get("/zones/{zone_id}/snapshot")
async def get_zone_snapshot(zone_id: str) -> dict:
    return zone_snapshot(zone_id, restaurants.values(), riders.values(), orders.values())


@router.post("/maps/fragments/nearby")
async def nearby_map_distribution(payload: MapFragmentRequestIn) -> dict:
    fragments = nearby_map_fragments(payload.location, payload.radius_km, zones.values())
    installed = set(payload.installed_fragment_ids)
    plan = cache_plan(fragments, payload.max_cache_mb)
    return {
        "mode": "offline_first_osm",
        "provider": "openstreetmap",
        "tile_format": "vector_pbf",
        "routing_graph": "graphhopper-compatible",
        "tile_pack_ready": tile_store().is_ready(),
        "routing_graph_ready": get_settings().routing_graph.exists(),
        "device_id": payload.device_id,
        "active_order_id": payload.active_order_id,
        "radius_km": payload.radius_km,
        "current_zone_id": micro_zone_id(payload.location),
        "download_fragment_ids": [
            fragment["fragment_id"]
            for fragment in fragments
            if fragment["fragment_id"] in plan["keep_fragment_ids"] and fragment["fragment_id"] not in installed
        ],
        "fragments": fragments,
        "cache_plan": plan,
    }


@router.get("/maps/fragments/{fragment_id}/manifest")
async def map_fragment_manifest(fragment_id: str) -> dict:
    center = fragment_center(fragment_id)
    manifest = fragment_manifest(fragment_id, center, 0.0, zones.values())
    manifest["tile_pack_ready"] = tile_store().is_ready()
    manifest["routing_graph_ready"] = get_settings().routing_graph.exists()
    return manifest


@router.get("/maps/tiles/{z}/{x}/{y}.pbf")
async def vector_tile(z: int, x: int, y: int) -> Response:
    tile = tile_store().tile(z, x, y)
    if tile is None:
        raise HTTPException(status_code=404, detail="Vector tile not found. Install the MBTiles map pack first.")
    return Response(
        content=tile,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Content-Encoding": "gzip", "Cache-Control": "public, max-age=86400"},
    )


@router.get("/maps/fragments/{fragment_id}/tiles/{z}/{x}/{y}.pbf")
async def fragment_vector_tile(fragment_id: str, z: int, x: int, y: int) -> Response:
    return await vector_tile(z, x, y)


@router.get("/maps/tilejson.json")
async def map_tilejson(request: Request) -> dict:
    store = tile_store()
    if not store.is_ready():
        raise HTTPException(status_code=404, detail="Vector tile MBTiles file is not installed")
    base_url = str(request.base_url).rstrip("/")
    return store.tilejson(base_url)


@router.get("/maps/style.json")
async def map_style(request: Request) -> dict:
    base_url = str(request.base_url).rstrip("/")
    return {
        "version": 8,
        "name": "FOODTRUCK Offline OSM",
        "glyphs": f"{base_url}/api/maps/fonts/{{fontstack}}/{{range}}.pbf",
        "sources": {
            "foodtruck-osm": {
                "type": "vector",
                "url": f"{base_url}/api/maps/tilejson.json",
            }
        },
        "layers": [
            {"id": "background", "type": "background", "paint": {"background-color": "#f7f3ea"}},
            {
                "id": "ocean",
                "type": "fill",
                "source": "foodtruck-osm",
                "source-layer": "ocean",
                "paint": {"fill-color": "#9bd3e6"},
            },
            {
                "id": "water-polygons",
                "type": "fill",
                "source": "foodtruck-osm",
                "source-layer": "water_polygons",
                "paint": {"fill-color": "#9bd3e6"},
            },
            {
                "id": "landuse",
                "type": "fill",
                "source": "foodtruck-osm",
                "source-layer": "land",
                "paint": {"fill-color": "#efe6d0", "fill-opacity": 0.45},
            },
            {
                "id": "buildings",
                "type": "fill",
                "source": "foodtruck-osm",
                "source-layer": "buildings",
                "paint": {"fill-color": "#d6c2a4", "fill-opacity": 0.55},
            },
            {
                "id": "street-casing",
                "type": "line",
                "source": "foodtruck-osm",
                "source-layer": "streets",
                "paint": {"line-color": "#d4a373", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 14, 4.8]},
            },
            {
                "id": "streets",
                "type": "line",
                "source": "foodtruck-osm",
                "source-layer": "streets",
                "paint": {"line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 3.2]},
            },
        ],
    }


@router.get("/maps/fragments/{fragment_id}/graph")
async def routing_graph_manifest(fragment_id: str) -> dict:
    graph_dir = get_settings().routing_graph
    if not graph_dir.exists():
        raise HTTPException(status_code=404, detail="Routing graph is not installed. Build/import GraphHopper graph files first.")
    return {
        "fragment_id": fragment_id,
        "engine": "graphhopper-compatible",
        "graph_dir": str(graph_dir),
        "ready": True,
    }


@router.get("/maps/zones/active")
async def active_delivery_zones() -> List[dict]:
    return [
        {
            **zone,
            "zone_id": zone["id"],
            "tile_fragment_id": osm_fragment_id(zone["center"]),
        }
        for zone in zones.values()
    ]


@router.post("/dispatch/plan")
async def dispatch_plan(payload: DispatchPlanIn) -> dict:
    restaurant = restaurants.get(payload.restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    pickup = restaurant["location"]
    zone_id = micro_zone_id(payload.delivery_location)
    candidate = assign_rider(riders.values(), pickup, payload.delivery_location)
    batching = build_batch_candidates(payload.restaurant_id, zone_id)
    pricing_breakdown = calculate_pricing(
        payload.food_amount,
        payload.distance_km,
        traffic_multiplier=zone_traffic_index(zone_id),
        rider_availability_index=rider_availability_index(zone_id),
        batching_discount=8.0 if batching else 0.0,
    )
    return {
        "mode": "logistics_first",
        "hold_seconds": payload.hold_seconds,
        "zone_id": zone_id,
        "selected_rider": candidate,
        "batching_candidates": batching,
        "pricing": pricing_breakdown.model_dump(),
        "decision": "hold_for_batching" if batching else "assign_operationally_best_rider",
    }


@router.post("/orders")
async def create_order(payload: OrderIn) -> dict:
    order_id = str(uuid4())
    restaurant = restaurants.get(payload.restaurant_id)
    target_zone_id = payload.target_zone_id or micro_zone_id(payload.delivery_location)
    batching = build_batch_candidates(payload.restaurant_id, target_zone_id)
    pricing_breakdown = calculate_pricing(
        payload.food_amount,
        payload.distance_km,
        traffic_multiplier=zone_traffic_index(target_zone_id),
        rider_availability_index=rider_availability_index(target_zone_id),
        batching_discount=8.0 if batching else 0.0,
    ).model_dump()
    assigned = assign_rider(riders.values(), restaurant["location"], payload.delivery_location) if restaurant else None
    orders[order_id] = {
        "id": order_id,
        **payload.model_dump(),
        "pricing": pricing_breakdown,
        "rider": assigned,
        "status": "held" if batching else "created",
        "target_zone_id": target_zone_id,
        "hold_until_seconds": 12 if batching else 0,
        "batching_candidates": batching,
        "picked_up_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(f"order:{order_id}", {"type": "order_created", "payload": orders[order_id]})
    return orders[order_id]


@router.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, payload: OrderStatusIn) -> dict:
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["status"] = payload.status
    if payload.status == "picked_up" and not order["picked_up_at"]:
        order["picked_up_at"] = datetime.now(timezone.utc).isoformat()
    if payload.rider_location:
        order["last_rider_location"] = payload.rider_location.model_dump()
    await manager.broadcast(f"order:{order_id}", {"type": "order_status", "payload": order})
    return order


@router.get("/orders/{order_id}/tracking")
async def order_tracking(order_id: str) -> dict:
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    timer_active = order["picked_up_at"] is not None
    return {
        "order_id": order_id,
        "status": order["status"],
        "timer_active": timer_active,
        "picked_up_at": order["picked_up_at"],
        "rider": order.get("rider"),
        "last_rider_location": order.get("last_rider_location"),
        "eta_minutes": 18 if timer_active else None,
    }


@router.get("/orders/batching/candidates")
async def batching_candidates(restaurant_id: str) -> List[dict]:
    restaurant = restaurants.get(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    zone_id = micro_zone_id(restaurant["location"])
    return build_batch_candidates(restaurant_id, zone_id)


def build_batch_candidates(restaurant_id: str, zone_id: str) -> List[dict]:
    open_orders = [
        order for order in orders.values()
        if order["restaurant_id"] == restaurant_id
        and order.get("target_zone_id") == zone_id
        and order["status"] in {"held", "created", "accepted", "preparing"}
    ]
    return [
        {
            "batch_id": str(uuid4()),
            "restaurant_id": restaurant_id,
            "zone_id": zone_id,
            "order_ids": [order["id"] for order in open_orders[:3]],
            "pickup_sequence": [restaurant_id],
            "drop_sequence": [order["delivery_location"] for order in open_orders[:3]],
            "efficiency_gain_percent": min(28, 10 + len(open_orders) * 6),
            "reason": "Clustered delivery zone with compatible drop direction",
        }
    ] if len(open_orders) > 1 else []


def zone_traffic_index(zone_id: str) -> float:
    zone = zones.get(zone_id)
    return float(zone.get("traffic_index", 1.0)) if zone else 1.0


def rider_availability_index(zone_id: str) -> float:
    snapshot = zone_snapshot(zone_id, restaurants.values(), riders.values(), orders.values())
    density = float(snapshot["delivery_density"])
    if density >= 2:
        return 1.25
    if density < 0.5:
        return 0.92
    return 1.0


@router.websocket("/ws/orders/{order_id}")
async def order_socket(websocket: WebSocket, order_id: str) -> None:
    room = f"order:{order_id}"
    await manager.connect(room, websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            await manager.broadcast(room, payload)
    except WebSocketDisconnect:
        manager.disconnect(room, websocket)


@router.get("/analytics/rider/{rider_id}", response_model=AnalyticsOut)
async def rider_analytics(rider_id: str) -> AnalyticsOut:
    return AnalyticsOut(
        daily=1260,
        weekly=8420,
        monthly=32780,
        financial_year=318400,
        orders=148,
        rating=4.86,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/analytics/restaurant/{restaurant_id}", response_model=AnalyticsOut)
async def restaurant_analytics(restaurant_id: str) -> AnalyticsOut:
    return AnalyticsOut(
        daily=18420,
        weekly=118500,
        monthly=498900,
        financial_year=4380000,
        orders=932,
        rating=4.74,
        updated_at=datetime.now(timezone.utc),
    )
