# Weather Dashboard — FastAPI Backend

Real-time weather backend powered by **OpenWeatherMap** with REST endpoints and WebSocket live updates.

---

## Tech Stack

| Layer | Library |
|---|---|
| Framework | FastAPI |
| HTTP Client | httpx (async) |
| WebSocket | FastAPI native (starlette) |
| Config | pydantic-settings |
| Server | uvicorn |

---

## Project Structure

```
weather-backend/
├── main.py               # App entry point, WebSocket endpoint, background broadcaster
├── config.py             # Settings (reads from .env)
├── websocket_manager.py  # Manages active WS connections + location metadata
├── routers/
│   ├── weather.py        # GET /api/weather/current  +  /api/weather/search
│   └── forecast.py       # GET /api/forecast/hourly  +  /api/forecast/daily
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
# 1. Clone / copy project
cd weather-backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env
# Edit .env and paste your OWM key

# 5. Run
uvicorn main:app --reload --port 8000
```

Get a free API key at https://openweathermap.org/api

---

## API Reference

### REST Endpoints

#### Current Weather
```
GET /api/weather/current?city=London
GET /api/weather/current?lat=51.5&lon=-0.1
```

**Response:**
```json
{
  "city": "London",
  "country": "GB",
  "temp": 14.2,
  "feels_like": 12.8,
  "humidity": 72,
  "wind": { "speed": 5.1, "deg": 240 },
  "weather": { "description": "overcast clouds", "icon_url": "..." },
  "sun": { "sunrise": 1700000000, "sunset": 1700040000 },
  "cached": false
}
```

#### City Search (Autocomplete)
```
GET /api/weather/search?q=Mumb
```

#### Hourly Forecast
```
GET /api/forecast/hourly?city=Delhi&hours=24
```
Returns 3-hour interval slots for the next N hours.

#### Daily Forecast
```
GET /api/forecast/daily?city=Delhi&days=5
```
Returns aggregated daily summaries (min/max/avg temp, rain, pop).

---

### WebSocket

```
ws://localhost:8000/ws/weather?city=London
ws://localhost:8000/ws/weather?lat=28.6&lon=77.2
```

**On connect:** immediately receives current weather JSON.  
**Every 60 s:** server pushes a fresh update automatically.

**Change location at runtime** (send from client):
```json
{ "type": "change_location", "city": "Mumbai" }
{ "type": "change_location", "lat": 19.07, "lon": 72.87 }
```

**Update payload shape:**
```json
{
  "type": "weather_update",
  "city": "London",
  "temp": 14.2,
  "humidity": 72,
  "wind_speed": 5.1,
  "description": "overcast clouds",
  "icon": "04d",
  "dt": 1700000000
}
```

---

## Interactive Docs

Once running, visit:
- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

---

## Caching

Current weather responses are cached in-memory for **5 minutes** (configurable via `CACHE_TTL_SECONDS` in `.env`) to avoid hitting OWM rate limits.

---

## CORS

CORS is open (`allow_origins=["*"]`) for development. Before deploying, restrict it in `main.py`:

```python
allow_origins=["https://your-frontend-domain.com"]
```
