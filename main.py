import asyncio
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional

from config import settings
from routers import weather, forecast
from websocket_manager import ConnectionManager

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task that pushes weather updates to all connected WS clients
    task = asyncio.create_task(broadcast_weather_updates())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Weather Dashboard API",
    description="Real-time weather backend powered by OpenWeatherMap",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weather.router, prefix="/api/weather", tags=["Weather"])
app.include_router(forecast.router, prefix="/api/forecast", tags=["Forecast"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "Weather Dashboard API is running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "connected_clients": manager.active_count()}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/weather")
async def weather_websocket(
    websocket: WebSocket,
    city: Optional[str] = Query(default="London"),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
):
    """
    Connect and receive live weather updates every 60 seconds.

    Query params (use one):
      - city=London
      - lat=51.5&lon=-0.1
    """
    await manager.connect(websocket, city=city, lat=lat, lon=lon)
    try:
        # Send an immediate update on connection
        data = await fetch_weather_for_client(city=city, lat=lat, lon=lon)
        await websocket.send_json(data)

        # Keep the connection alive; listen for client messages (ping / city change)
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "change_location":
                new_city = msg.get("city")
                new_lat = msg.get("lat")
                new_lon = msg.get("lon")
                manager.update_location(websocket, city=new_city, lat=new_lat, lon=new_lon)
                fresh = await fetch_weather_for_client(city=new_city, lat=new_lat, lon=new_lon)
                await websocket.send_json(fresh)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def fetch_weather_for_client(
    city: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict:
    """Fetch current weather from OWM and return a JSON-serialisable dict."""
    base = "https://api.openweathermap.org/data/2.5/weather"
    params = {"appid": settings.OWM_API_KEY, "units": "metric"}

    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon})
    else:
        params["q"] = city or "London"

    async with httpx.AsyncClient() as client:
        resp = await client.get(base, params=params, timeout=10)
        if resp.status_code != 200:
            return {"type": "error", "message": "Failed to fetch weather data"}
        raw = resp.json()

    return {
        "type": "weather_update",
        "city": raw["name"],
        "country": raw["sys"]["country"],
        "temp": raw["main"]["temp"],
        "feels_like": raw["main"]["feels_like"],
        "humidity": raw["main"]["humidity"],
        "pressure": raw["main"]["pressure"],
        "wind_speed": raw["wind"]["speed"],
        "wind_deg": raw["wind"].get("deg", 0),
        "description": raw["weather"][0]["description"],
        "icon": raw["weather"][0]["icon"],
        "visibility": raw.get("visibility", 0),
        "clouds": raw["clouds"]["all"],
        "sunrise": raw["sys"]["sunrise"],
        "sunset": raw["sys"]["sunset"],
        "dt": raw["dt"],
    }


async def broadcast_weather_updates():
    """Background task: refresh and push weather to every connected client every 60 s."""
    while True:
        await asyncio.sleep(60)
        for ws, meta in list(manager.clients.items()):
            try:
                data = await fetch_weather_for_client(
                    city=meta.get("city"),
                    lat=meta.get("lat"),
                    lon=meta.get("lon"),
                )
                await ws.send_json(data)
            except Exception:
                manager.disconnect(ws)