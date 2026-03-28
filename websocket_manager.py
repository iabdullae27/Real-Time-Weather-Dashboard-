from fastapi import WebSocket
from typing import Optional


class ConnectionManager:
    """Tracks active WebSocket connections and their associated location metadata."""

    def __init__(self):
        # ws -> {"city": ..., "lat": ..., "lon": ...}
        self.clients: dict[WebSocket, dict] = {}

    async def connect(
        self,
        websocket: WebSocket,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ):
        await websocket.accept()
        self.clients[websocket] = {"city": city, "lat": lat, "lon": lon}
        print(f"[WS] Client connected. Total: {self.active_count()}")

    def disconnect(self, websocket: WebSocket):
        self.clients.pop(websocket, None)
        print(f"[WS] Client disconnected. Total: {self.active_count()}")

    def update_location(
        self,
        websocket: WebSocket,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ):
        if websocket in self.clients:
            self.clients[websocket] = {"city": city, "lat": lat, "lon": lon}

    def active_count(self) -> int:
        return len(self.clients)

    async def broadcast(self, message: dict):
        """Send the same message to every connected client."""
        for ws in list(self.clients.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)