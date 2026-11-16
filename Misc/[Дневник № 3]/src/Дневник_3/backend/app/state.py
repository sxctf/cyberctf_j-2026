import random
from fastapi import WebSocket


class AppState:
    def __init__(self):
        self.rooms = {}   # room_id -> {ws: (cx, cy)}
        self.sync = {}    # room_id -> int

    def create_room(self, room_id: str):
        self.rooms[room_id] = {}
        self.sync[room_id] = 0

    def delete_room(self, room_id: str):
        self.rooms.pop(room_id, None)
        self.sync.pop(room_id, None)

    def connect(self, room: str, ws: WebSocket):
        if room not in self.rooms:
            self.create_room(room)

        self.rooms[room][ws] = (0, 0)
        self.recalculate_sync(room)

    def disconnect(self, room: str, ws: WebSocket):
        if room in self.rooms:
            self.rooms[room].pop(ws, None)

            if not self.rooms[room]:
                self.delete_room(room)
            else:
                self.recalculate_sync(room)

    def update_position(self, room: str, ws: WebSocket, cx: float, cy: float):
        self.rooms[room][ws] = (cx, cy)

    def get_points(self, room: str):
        return list(self.rooms.get(room, {}).values())

    def count(self, room: str):
        return len(self.rooms.get(room, {}))

    def recalculate_sync(self, room: str):
        count = len(self.rooms[room])

        if count == 0:
            self.sync[room] = 0
        elif count < 3:
            self.sync[room] = random.randint(1, 98)
        elif count == 3:
            self.sync[room] = 99
        else:
            self.sync[room] = random.randint(101, 150)


state = AppState()