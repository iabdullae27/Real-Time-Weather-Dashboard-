import httpx
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from config import settings

router = APIRouter()


async def _owm_request(endpoint: str, params: dict) -> dict:
    params["appid"] = settings.OWM_API_KEY
    params["units"] = "metric"
    url = f"{settings.OWM_BASE_URL}/{endpoint}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid OpenWeatherMap API key.")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Location not found.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Upstream weather service error.")
    return resp.json()


def _location_params(
    city: Optional[str], lat: Optional[float], lon: Optional[float]
) -> dict:
    if lat is not None and lon is not None:
        return {"lat": lat, "lon": lon}
    return {"q": city or "London"}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/hourly")
async def get_hourly_forecast(
    city: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    hours: int = Query(default=24, ge=3, le=120, description="Number of hours ahead (max 120)"),
):
    """
    Hourly forecast using OWM's 3-hour step free-tier endpoint.
    Returns up to `hours` worth of 3-hourly data points.
    """
    params = _location_params(city, lat, lon)
    # OWM free tier gives 5-day / 3-hour forecast (40 slots)
    params["cnt"] = min((hours // 3) + 1, 40)

    raw = await _owm_request("forecast", params)

    slots = []
    for item in raw["list"]:
        slots.append({
            "dt": item["dt"],
            "time": datetime.utcfromtimestamp(item["dt"]).strftime("%Y-%m-%d %H:%M UTC"),
            "temp": item["main"]["temp"],
            "feels_like": item["main"]["feels_like"],
            "humidity": item["main"]["humidity"],
            "wind_speed": item["wind"]["speed"],
            "pop": round(item.get("pop", 0) * 100),  # probability of precipitation %
            "rain_3h": item.get("rain", {}).get("3h", 0),
            "snow_3h": item.get("snow", {}).get("3h", 0),
            "description": item["weather"][0]["description"],
            "icon": item["weather"][0]["icon"],
            "icon_url": f"https://openweathermap.org/img/wn/{item['weather'][0]['icon']}@2x.png",
        })

    return {
        "city": raw["city"]["name"],
        "country": raw["city"]["country"],
        "timezone_offset": raw["city"]["timezone"],
        "hourly": slots,
    }


@router.get("/daily")
async def get_daily_forecast(
    city: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    days: int = Query(default=5, ge=1, le=5, description="Number of days (max 5 on free tier)"),
):
    """
    Daily summary derived from OWM's 3-hourly forecast.
    Groups 3-hour slots by UTC date and computes daily min/max/avg.
    """
    params = _location_params(city, lat, lon)
    params["cnt"] = 40  # fetch all 40 slots then group

    raw = await _owm_request("forecast", params)

    # Group by date
    by_day: dict[str, list] = {}
    for item in raw["list"]:
        date_str = datetime.utcfromtimestamp(item["dt"]).strftime("%Y-%m-%d")
        by_day.setdefault(date_str, []).append(item)

    daily = []
    for date_str, slots in sorted(by_day.items())[:days]:
        temps = [s["main"]["temp"] for s in slots]
        pops = [s.get("pop", 0) for s in slots]
        # Pick the most representative slot (noon or closest)
        noon_slot = min(slots, key=lambda s: abs(
            datetime.utcfromtimestamp(s["dt"]).hour - 12
        ))

        daily.append({
            "date": date_str,
            "temp_min": round(min(temps), 1),
            "temp_max": round(max(temps), 1),
            "temp_avg": round(sum(temps) / len(temps), 1),
            "humidity_avg": round(sum(s["main"]["humidity"] for s in slots) / len(slots)),
            "wind_speed_avg": round(sum(s["wind"]["speed"] for s in slots) / len(slots), 1),
            "pop_max": round(max(pops) * 100),
            "description": noon_slot["weather"][0]["description"],
            "icon": noon_slot["weather"][0]["icon"],
            "icon_url": f"https://openweathermap.org/img/wn/{noon_slot['weather'][0]['icon']}@2x.png",
            "total_rain_mm": round(sum(s.get("rain", {}).get("3h", 0) for s in slots), 1),
        })

    return {
        "city": raw["city"]["name"],
        "country": raw["city"]["country"],
        "daily": daily,
    }