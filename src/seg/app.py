from __future__ import annotations

from fastapi import FastAPI

from .config import Settings
from .routes.health import router as health_router
from .routes.metrics import router as metrics_router

settings = Settings()

app = FastAPI(title="Secure Execution Gateway (SEG)", version="0.1.0")

app.state.settings = settings

app.include_router(health_router)
app.include_router(metrics_router)
