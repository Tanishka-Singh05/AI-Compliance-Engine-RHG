import os

from fastapi import FastAPI

from rhg.api.agentic_routes import router as agentic_router
from rhg.api.routes import router

app = FastAPI(title="RHG — Release Hardening Gate", version="2.0.0")
app.include_router(router)
app.include_router(agentic_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rhg"}


@app.on_event("startup")
async def startup():
    if os.environ.get("RHG_METRICS_ENABLED", "true").lower() == "true":
        try:
            from ace.metrics.prometheus import start_metrics_server

            port = int(os.environ.get("RHG_METRICS_PORT", "9091"))
            start_metrics_server(port)
        except RuntimeError:
            pass
