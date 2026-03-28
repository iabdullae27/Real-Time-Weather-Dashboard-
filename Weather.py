import httpx
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from functools import lru_cache
import time

from config import settings

router = APIRouter()

# Simple in-memory cache: key -> (data, timestamp)
_cache: dict[str, tuple[dict, float]] = {}


def _cache_key(city: Optional[str], lat: Optional[float], lon: Optional[float]) -> str:
    if lat is not None and lon is not None:
        return f"coords:{lat},{lon}"
    return f"city:{(city or 'London').lower()}"


def _get_cached(key: str) -> Optional[dict]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[1]) < settings.CACHE_TTL_SECONDS:
        return entry[0]
    return None


def _set_cached(key: str, data: dict):
    _cache[key] = (data, time.time())


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/current")
async def get_current_weather(
    city: Optional[str] = Query(default=None, description="City name e.g. London"),
    lat: Optional[float] = Query(default=None, description="Latitude"),
    lon: Optional[float] = Query(default=None, description="Longitude"),
):
    """
    Fetch current weather.

    Priority: lat/lon > city. Defaults to London if nothing is provided.
    """
    if lat is None and lon is None and city is None:
        city = "London"

    key = _cache_key(city, lat, lon)
    cached = _get_cached(key)
    if cached:
        return {**cached, "cached": True}

    params = {}
    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon})
    else:
        params["q"] = city

    raw = await _owm_request("weather", params)

    result = {
        "city": raw["name"],
        "country": raw["sys"]["country"],
        "coord": {"lat": raw["coord"]["lat"], "lon": raw["coord"]["lon"]},
        "temp": raw["main"]["temp"],
        "feels_like": raw["main"]["feels_like"],
        "temp_min": raw["main"]["temp_min"],
        "temp_max": raw["main"]["temp_max"],
        "humidity": raw["main"]["humidity"],
        "pressure": raw["main"]["pressure"],
        "visibility": raw.get("visibility", 0),
        "wind": {
            "speed": raw["wind"]["speed"],
            "deg": raw["wind"].get("deg", 0),
            "gust": raw["wind"].get("gust"),
        },
        "clouds": raw["clouds"]["all"],
        "weather": {
            "id": raw["weather"][0]["id"],
            "main": raw["weather"][0]["main"],
            "description": raw["weather"][0]["description"],
            "icon": raw["weather"][0]["icon"],
            "icon_url": f"https://openweathermap.org/img/wn/{raw['weather'][0]['icon']}@2x.png",
        },
        "sun": {
            "sunrise": raw["sys"]["sunrise"],
            "sunset": raw["sys"]["sunset"],
        },
        "dt": raw["dt"],
        "timezone": raw["timezone"],
        "cached": False,
    }

    _set_cached(key, result)
    return result


@router.get("/search")
async def search_cities(q: str = Query(..., min_length=2, description="City name to search")):
    """
    Search for cities by name using OWM Geocoding API.
    Returns up to 5 matching locations with coordinates.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": q, "limit": 5, "appid": settings.OWM_API_KEY},
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Geocoding service error.")

    results = resp.json()
    return [
        {
            "name": r["name"],
            "state": r.get("state", ""),
            "country": r["country"],
            "lat": r["lat"],
            "lon": r["lon"],
        }
        for r in results
    ]