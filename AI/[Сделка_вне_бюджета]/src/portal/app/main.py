"""Task 06 — Browser Agent Attack — web portal."""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes.pages import router as pages_router
from .routes.events import router as events_router

app = FastAPI(title="Task 06 — Browser Agent Attack", docs_url=None, redoc_url=None)
app.include_router(pages_router)
app.include_router(events_router)

_vendor = os.path.join(os.path.dirname(__file__), "vendor")
if _vendor and os.path.isdir(_vendor):
    app.mount("/vendor", StaticFiles(directory=_vendor), name="vendor")


@app.get("/health")
def health():
    return {"status": "ok", "task": "06-browser-agent"}
