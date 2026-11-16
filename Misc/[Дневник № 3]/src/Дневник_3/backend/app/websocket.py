import json
import re
from fastapi import WebSocket, WebSocketDisconnect
from app.state import state
from app.geometry import check_triangle
from app.config import TTP, REQUIRED_CLIENTS, MAX_CLIENTS

UUID_RE = re.compile(r"^[a-f0-9\-]{36}$")

async def websocket_endpoint(ws: WebSocket):
    room = ws.query_params.get("room")

    # ✅ 1. Валидация room
    if not room or not UUID_RE.match(room):
        await ws.close()
        return

    # ✅ 2. Проверка лимита клиентов
    if state.count(room) >= MAX_CLIENTS:
        await ws.close()
        return

    await ws.accept()

    state.connect(room, ws)

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)

            cx = data.get("cx")
            cy = data.get("cy")

            state.update_position(room, ws, cx, cy)

            points = state.get_points(room)
            count = state.count(room)

            solved = False
            if count == REQUIRED_CLIENTS:
                solved = check_triangle(points)

            sync = 100 if solved else state.sync[room]

            # другие клиенты
            others = []
            for other_ws, (ox, oy) in state.rooms[room].items():
                if other_ws != ws:
                    others.append({
                        "cx": ox,
                        "cy": oy
                    })

            response = {
                "type": "state",
                "sync": sync,
                "zero": solved,
                "others": others
            }

            if solved:
                response["ttp"] = TTP

            await ws.send_text(json.dumps(response))

    except WebSocketDisconnect:
        state.disconnect(room, ws)