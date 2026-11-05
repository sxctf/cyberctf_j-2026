"""Task 07 — Poisoned MCP Marketplace — web portal."""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes.pages import router as pages_router
from .routes.events import router as events_router

app = FastAPI(title="Task 07 — Poisoned MCP", docs_url=None, redoc_url=None)
app.include_router(pages_router)
app.include_router(events_router)

# Vendored JS (htmx, tailwind, mermaid) — served locally, no CDN required.
_vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
if _vendor_dir and os.path.isdir(_vendor_dir):
    app.mount("/vendor", StaticFiles(directory=_vendor_dir), name="vendor")


@app.get("/health")
def health():
    return {"status": "ok", "task": "07-poisoned-mcp"}
