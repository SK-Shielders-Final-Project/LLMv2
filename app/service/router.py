from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.service.registry import (
    get_available_bikes,
    get_inquiries,
    get_notices,
    get_nearby_stations,
    get_payments,
    get_rentals,
    get_total_payments,
    get_total_usage,
    get_user_profile,
)

router = APIRouter()


@router.get("/getUserProfile")
def get_user_profile_api(user_id: int) -> dict[str, Any]:
    return get_user_profile(user_id)


@router.get("/getRentals")
def get_rentals_api(user_id: int, days: int = 7) -> list[dict[str, Any]]:
    return get_rentals(user_id=user_id, days=days)


@router.get("/getPayments")
def get_payments_api(user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return get_payments(user_id=user_id, limit=limit)


@router.get("/getNearbyStations")
def get_nearby_stations_api(lat: float, lon: float) -> list[dict[str, Any]]:
    return get_nearby_stations(lat=lat, lon=lon)

@router.get("/getAvailableBikes")
def get_available_bikes_api(
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 1.0,
) -> list[dict[str, Any]]:
    return get_available_bikes(lat=lat, lon=lon, radius_km=radius_km)


@router.get("/getNotices")
def get_notices_api(limit: int = 5) -> list[dict[str, Any]]:
    return get_notices(limit=limit)

@router.get("/getInquiries")
def get_inquiries_api(user_id: int) -> list[dict[str, Any]]:
    return get_inquiries(user_id=user_id)

@router.get("/getTotalPayments")
def get_total_payments_api(user_id: int) -> dict[str, Any]:
    return get_total_payments(user_id=user_id)

@router.get("/getTotalUsage")
def get_total_usage_api(user_id: int) -> dict[str, Any]:
    return get_total_usage(user_id=user_id)

