"""Task 05 — Code Agent Injection — web portal."""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes.pages import router as pages_router
from .routes.events import router as events_router

app = FastAPI(title="Task 05 — Code Agent Attack", docs_url=None, redoc_url=None)

_static = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static):
    app.mount("/static", StaticFiles(directory=_static), name="static")

_vendor = os.path.join(os.path.dirname(__file__), "vendor")
if _vendor and os.path.isdir(_vendor):
    app.mount("/vendor", StaticFiles(directory=_vendor), name="vendor")

app.include_router(pages_router)
app.include_router(events_router)

@app.get("/health")
def health():
    return {"status": "ok", "task": "05-code-agent"}
