from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import api, pages
from app.services import state_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    state_store.initialize_state("0")
    yield


app = FastAPI(
    title="TritonWebMid: эскалация через shared memory",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/health")
async def health():
    state_store.initialize_state()
    return {"status": "ok", "service": "tritonwebmid-shared-memory-chain"}
