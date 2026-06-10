import math

from app.models.schemas import PricingOut


def delivery_fee(distance_km: float, traffic_multiplier: float = 1.0, rider_availability_index: float = 1.0, batching_discount: float = 0.0) -> float:
    if distance_km <= 3:
        base = 30.0
    else:
        base = 30.0 + math.ceil(distance_km - 3) * 10.0
    semi_dynamic = base * traffic_multiplier * rider_availability_index
    return round(max(25.0, semi_dynamic - batching_discount), 2)


def calculate_pricing(
    food_amount: float,
    distance_km: float,
    traffic_multiplier: float = 1.0,
    rider_availability_index: float = 1.0,
    batching_discount: float = 0.0,
) -> PricingOut:
    delivery = delivery_fee(distance_km, traffic_multiplier, rider_availability_index, batching_discount)
    platform = round((food_amount + delivery) * 0.04, 2)
    food_gst = round(food_amount * 0.05, 2)
    delivery_gst = round(delivery * 0.18, 2)
    platform_gst = round(platform * 0.18, 2)
    total = round(food_amount + food_gst + delivery + delivery_gst + platform + platform_gst, 2)
    rider_earning = round(delivery + platform * 0.005, 2)
    return PricingOut(
        food_amount=round(food_amount, 2),
        food_gst=food_gst,
        delivery_fee=delivery,
        delivery_gst=delivery_gst,
        platform_fee=platform,
        platform_gst=platform_gst,
        total_payable=total,
        rider_earning=rider_earning,
    )
