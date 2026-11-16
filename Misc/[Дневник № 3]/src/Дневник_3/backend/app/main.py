from fastapi import FastAPI, WebSocket  # 👈 добавь WebSocket
from app.websocket import websocket_endpoint
import uuid
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/session")
async def create_session():
    room_id = str(uuid.uuid4())
    return {"room": room_id}

@app.websocket("/ws")
async def ws_route(ws: WebSocket):  # 👈 ВОТ ТУТ тип
    await websocket_endpoint(ws)