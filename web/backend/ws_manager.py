"""WebSocket connection manager for verification result push."""
import json
from typing import Dict, Set

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, message_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(message_id, set()).add(websocket)

    def disconnect(self, message_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(message_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            del self._connections[message_id]

    async def broadcast(self, message_id: str, payload: dict) -> None:
        conns = list(self._connections.get(message_id, set()))
        dead = []
        text = json.dumps(payload, ensure_ascii=False)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(message_id, ws)


_ws_manager = WSManager()


def get_ws_manager() -> WSManager:
    return _ws_manager
