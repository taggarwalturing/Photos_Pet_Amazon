"""
WebSocket connection manager for real-time lock broadcasts.

All annotator clients connect via WS. When a lock event occurs
(acquire / release / save), the server broadcasts to ALL connected
clients so they can update their UI immediately.
"""
from __future__ import annotations
import asyncio
import json
from fastapi import WebSocket
from typing import Optional


class ConnectionManager:
    """Manages WebSocket connections for annotator lock broadcasts."""

    def __init__(self):
        # user_id → set of WebSocket connections (one user can have multiple tabs)
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: int):
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    del self._connections[user_id]

    async def broadcast(self, message: dict, exclude_user_id: Optional[int] = None):
        """Send a message to ALL connected clients except the excluded user."""
        payload = json.dumps(message)
        async with self._lock:
            targets = []
            for uid, conns in self._connections.items():
                if uid == exclude_user_id:
                    continue
                for ws in conns:
                    targets.append(ws)

        # Send outside the lock to avoid holding it during I/O
        stale = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)

        # Clean up broken connections
        if stale:
            async with self._lock:
                for uid, conns in list(self._connections.items()):
                    for ws in stale:
                        conns.discard(ws)
                    if not conns:
                        del self._connections[uid]


# Singleton instance shared across the app
lock_manager = ConnectionManager()
