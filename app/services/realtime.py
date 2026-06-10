from typing import Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms.setdefault(room, set()).add(websocket)

    def disconnect(self, room: str, websocket: WebSocket) -> None:
        if room in self.rooms:
            self.rooms[room].discard(websocket)
            if not self.rooms[room]:
                self.rooms.pop(room)

    async def broadcast(self, room: str, payload: dict) -> None:
        for websocket in list(self.rooms.get(room, set())):
            await websocket.send_json(payload)


manager = ConnectionManager()
