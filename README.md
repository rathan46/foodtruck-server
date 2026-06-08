# FOODTRUCK Backend

FastAPI backend for customer, rider, restaurant, OTP, pricing, assignment, offline map distribution, analytics, and real-time order tracking.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Configure production values from `.env.example`. The API boots without MongoDB for local UI development, but production should set `MONGODB_URI` and `JWT_SECRET`.

## Main API coverage

- `POST /api/auth/request-otp` queues WhatsApp OTP jobs for the Python sender client.
- `POST /api/auth/verify-otp` validates OTPs and returns JWT bearer tokens.
- `POST /api/customers/addresses` stores Home, Work, and Other coordinates.
- `POST /api/restaurants`, `PATCH /api/restaurants/{id}/status`, and `POST /api/restaurants/offers` manage restaurant onboarding, open/closed state, and coupons.
- `POST /api/restaurants/menu` and `GET /api/restaurants/{id}/menu` manage product cards.
- `POST /api/pricing` returns food GST, delivery GST, platform fee, total payable, and rider earning.
- `POST /api/orders`, `PATCH /api/orders/{id}/status`, and `GET /api/orders/{id}/tracking` drive order lifecycle and live tracking.
- `GET /api/orders/batching/candidates?restaurant_id=...` returns smart batching suggestions for compatible open orders.
- `POST /api/riders/location` updates online rider GPS and broadcasts over WebSocket.
- `POST /api/maps/fragments/nearby` returns nearby OpenStreetMap vector-tile fragments, GraphHopper-compatible routing graph URLs, active/preload priorities, and client cache instructions.
- `GET /api/maps/fragments/{fragment_id}/manifest` returns metadata for one map fragment.
- `GET /api/maps/zones/active` returns active delivery zones with their map fragment IDs.

## Offline map operating model

FOODTRUCK should behave as a scalable hyperlocal logistics operating system, not as a thin Google Maps wrapper.

- Store complete India OSM extracts, generated vector tiles, routing graphs, and delivery-zone definitions on the backend.
- Distribute only local fragments to mobile devices, for example the rider's nearby 20 KM operating area.
- Preload upcoming fragments as riders move and evict stale fragments by expiry, distance, and least-recently-used priority.
- Use GraphHopper or a similar OSM routing engine for ETA, route optimization, batching, and rider assignment.
- Keep online Google Maps APIs optional for development or visual fallback, not required for core dispatch/navigation.

## Install real map data

The backend now serves local MBTiles vector maps. It does not scrape public OSM raster tiles.

```powershell
cd Server
.\scripts\download_southern_zone_maps.ps1
.\scripts\map_status.ps1
uvicorn app.main:app --reload
```

Verify after download:

- `GET /api/maps/tilejson.json`
- `GET /api/maps/style.json`
- `GET /api/maps/tiles/{z}/{x}/{y}.pbf`

Default tile path:

```text
Server/map_data/tiles/india-southern-zone-shortbread.mbtiles
```

For full India production coverage, repeat the same pattern with all required India regional MBTiles or generate one India-wide MBTiles package from `india-latest.osm.pbf`. Keep routing graph files under:

```text
Server/map_data/graphs/india-southern-zone/
```

## Verify

```powershell
python -m pytest
```
