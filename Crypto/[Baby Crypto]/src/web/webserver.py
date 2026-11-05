#!/usr/bin/env python3
                       
"""
Веб-витрина терминала "ШИФРАТОР".

Это ТОНКИЙ фронт: браузер по WebSocket подключается сюда, а сервер для каждого
клиента открывает обычное TCP-соединение к тому же самому server.py
(BACKEND_HOST:BACKEND_PORT) и просто перекачивает байты в обе стороны.

Следствие: веб и `nc` бьют в один и тот же процесс с одними и теми же секретами,
меню и уязвимостями. Решение (в т.ч. solve.py) от выбора интерфейса не зависит —
условия идентичны.

Зависимости: aiohttp (лёгкая). Статика — из ./static.
"""

import os
import asyncio
import pathlib

from aiohttp import web, WSMsgType

BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "1337"))
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

STATIC_DIR = pathlib.Path(__file__).parent / "static"


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "index.html")


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

                                                                      
    try:
        reader, writer = await asyncio.open_connection(BACKEND_HOST, BACKEND_PORT)
    except OSError:
        await ws.send_str("\r\n[СВЯЗЬ] Узел не отвечает. Линия недоступна.\r\n")
        await ws.close()
        return ws

    async def tcp_to_ws():
        """Поток от терминала -> в браузер."""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                if not ws.closed:
                    await ws.send_str(data.decode("utf-8", errors="replace"))
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if not ws.closed:
                await ws.close()

    pump = asyncio.create_task(tcp_to_ws())

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                                                                               
                writer.write(msg.data.encode("utf-8"))
                await writer.drain()
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        pump.cancel()
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
    return ws


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    return app


def main():
    app = build_app()
    print("[*] Веб-витрина ШИФРАТОР на http://%s:%d  (backend %s:%d)"
          % (WEB_HOST, WEB_PORT, BACKEND_HOST, BACKEND_PORT), flush=True)
    web.run_app(app, host=WEB_HOST, port=WEB_PORT, print=None)


if __name__ == "__main__":
    main()
