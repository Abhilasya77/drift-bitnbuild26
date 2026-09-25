"""Identity Continuity Platform — backend API (Team Drift, BitNBuild '26).

Run locally:   uvicorn app.main:app --reload      then open http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import init_db
from .routers import (profiles, documents, consistency, reviews, biometric, credentials, permanent,
                      notifications)
from .services import ocr, biometric as bio_service

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Identity Continuity Platform API",
    version="0.2.0",
    description=(
        "Team Drift · BitNBuild '26. Document evidence → cross-document consistency → exception-only human "
        "review → biometric verification → server-side eligibility → temporary credential → service verification "
        "→ renewal / permanent-credential transition.\n\n"
        "**Local dev auth:** click *Authorize* is not needed — add header `X-Demo-User: you@example.com` "
        "(Swagger: use the 'x-demo-user' field on each call). Reviewer = any email in REVIEWER_EMAILS."
    ),
)

app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=False)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "auth_mode": config.AUTH_MODE, "storage_mode": config.STORAGE_MODE,
            "ocr_available": ocr.tesseract_available(), "biometric_provider": bio_service.provider_name(),
            "database": config.DATABASE_URL.split(":", 1)[0]}


for r in (profiles, documents, consistency, reviews, biometric, credentials, permanent, notifications):
    app.include_router(r.router)
