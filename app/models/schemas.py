from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    customer = "customer"
    rider = "rider"
    restaurant = "restaurant"
    otp_sender = "otp_sender"


class Coordinate(BaseModel):
    lat: float
    lng: float


class OTPRequestIn(BaseModel):
    mobile: str = Field(min_length=10)
    role: Role


class OTPVerifyIn(BaseModel):
    mobile: str
    role: Role
    otp: str = Field(min_length=4, max_length=8)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class RestaurantIn(BaseModel):
    name: str
    owner_mobile: str
    location: Coordinate
    image_url: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    is_open: bool = True


class RestaurantStatusIn(BaseModel):
    is_open: bool


class AddressIn(BaseModel):
    customer_mobile: str
    label: str = Field(pattern="^(Home|Work|Other)$")
    address_line: str
    location: Coordinate


class OfferIn(BaseModel):
    restaurant_id: str
    code: str
    description: str
    discount_percent: float = Field(ge=0, le=100)
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: bool = True


class MenuItemIn(BaseModel):
    restaurant_id: str
    title: str
    subtitle: str = ""
    description: str = ""
    category: str
    price: float
    image_url: Optional[str] = None
    is_veg: bool = True
    is_available: bool = True


class PricingIn(BaseModel):
    food_amount: float
    distance_km: float
    traffic_multiplier: float = Field(default=1.0, ge=0.8, le=2.0)
    rider_availability_index: float = Field(default=1.0, ge=0.5, le=2.0)
    batching_discount: float = Field(default=0.0, ge=0.0, le=15.0)


class PricingOut(BaseModel):
    food_amount: float
    food_gst: float
    delivery_fee: float
    delivery_gst: float
    platform_fee: float
    platform_gst: float
    total_payable: float
    rider_earning: float


class OrderIn(BaseModel):
    customer_mobile: str
    restaurant_id: str
    items: List[dict]
    delivery_location: Coordinate
    food_amount: float
    distance_km: float
    target_zone_id: Optional[str] = None


class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(held|created|accepted|preparing|picked_up|on_route|delivered|cancelled)$")
    rider_location: Optional[Coordinate] = None


class RiderLocationIn(BaseModel):
    rider_id: str
    location: Coordinate
    is_online: bool = True
    rating: float = 4.8
    completed_orders: int = 0
    average_delivery_minutes: float = 28
    heading_degrees: float = Field(default=0, ge=0, le=360)
    active_load: int = Field(default=0, ge=0, le=4)
    idle_minutes: float = Field(default=0, ge=0)
    current_zone_id: Optional[str] = None


class ZoneIn(BaseModel):
    name: str
    center: Coordinate
    radius_km: float = Field(default=2.0, gt=0)
    demand_index: float = Field(default=1.0, ge=0)
    traffic_index: float = Field(default=1.0, ge=0.5, le=2.0)


class MapFragmentRequestIn(BaseModel):
    device_id: str
    location: Coordinate
    heading_degrees: float = Field(default=0, ge=0, le=360)
    radius_km: float = Field(default=20.0, ge=2.0, le=40.0)
    max_cache_mb: int = Field(default=512, ge=128, le=4096)
    active_order_id: Optional[str] = None
    installed_fragment_ids: List[str] = Field(default_factory=list)


class DispatchPlanIn(BaseModel):
    restaurant_id: str
    delivery_location: Coordinate
    food_amount: float
    distance_km: float
    hold_seconds: int = Field(default=12, ge=0, le=45)


class AnalyticsOut(BaseModel):
    daily: float
    weekly: float
    monthly: float
    financial_year: float
    orders: int
    rating: float
    updated_at: datetime
