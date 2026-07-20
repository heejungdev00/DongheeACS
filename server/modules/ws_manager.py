import json
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, data: dict):
        message = json.dumps(data, ensure_ascii=False)
        for ws in self.connections.copy():
            try:
                await ws.send_text(message)
            except:
                self.connections.remove(ws)