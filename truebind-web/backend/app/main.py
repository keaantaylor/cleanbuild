from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_origins
from .routes import alerts, audit, duplicates, exceptions, mapping, obligations, reports, templates, upload

app = FastAPI(title="Truebind API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router_module in (upload, mapping, reports, exceptions, duplicates, obligations, alerts, audit, templates):
    app.include_router(router_module.router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
