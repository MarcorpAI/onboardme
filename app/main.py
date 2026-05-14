"""
OnboardMe V2 — FastAPI Application Entry Point

Startup:
  1. Initialise database tables (create if not exist)
  2. Create/update default client record from env
  3. Seed default touchpoint templates

Routes:
  /webhook/*         — Onboard + inbound message handling
  /jobs/*            — Cron job endpoints
  /api/*             — Settings and configuration
"""

import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.routes import webhooks, jobs, settings
from app.config import settings as app_settings
from app.services.database import init_db, upsert_default_client, get_templates_for_client, upsert_template, sync_template_metadata
from app.services.journey import TOUCHPOINT_SCHEDULE, run_automation_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
automation_task = None

app = FastAPI(
    title="OnboardMe",
    description="AI-powered WhatsApp community onboarding engine — 90-day journey automation",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router)
app.include_router(jobs.router)
app.include_router(settings.router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.on_event("startup")
async def startup_event():
    """Initialize DB, create default client, seed templates."""
    logger.info("Starting OnboardMe V2...")

    # 1. Create tables
    await init_db()
    logger.info("Database tables ready")

    # 2. Create/update default client from env vars
    client = await upsert_default_client()
    client_id = client["id"]
    logger.info(f"Default client ready: {client_id} ({client['community_name']})")

    # 3. Seed default templates if they don't exist
    existing = await get_templates_for_client(client_id, include_inactive=True)
    existing_keys = {t["touchpoint_key"] for t in existing}

    seeded = 0
    for tp_def in TOUCHPOINT_SCHEDULE:
        key = tp_def["key"]
        if key not in existing_keys:
            await upsert_template(
                client_id=client_id,
                touchpoint_key=key,
                name=tp_def["name"],
                day=tp_def["day"],
                send_time=tp_def.get("send_time"),
                phase=tp_def["phase"],
                automation=tp_def["automation"],
                conditional=tp_def["conditional"],
                requires_human=tp_def["requires_human"],
                purpose=tp_def["purpose"],
                cta=tp_def["cta"],
                brief=tp_def["brief"],
                fallback_message=tp_def.get("fallback_message"),
                active=True,
            )
            seeded += 1
        else:
            await sync_template_metadata(
                client_id=client_id,
                touchpoint_key=key,
                name=tp_def["name"],
                day=tp_def["day"],
                phase=tp_def["phase"],
                automation=tp_def["automation"],
                conditional=tp_def["conditional"],
                requires_human=tp_def["requires_human"],
            )

    if seeded:
        logger.info(f"Seeded {seeded} new templates")
    else:
        logger.info("All templates already exist, nothing to seed")

    logger.info("OnboardMe V2 startup complete")

    global automation_task
    if automation_task is None:
        automation_task = asyncio.create_task(run_automation_loop())


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/")
async def root():
    return {
        "service": "OnboardMe",
        "description": "AI-powered WhatsApp community onboarding engine",
        "version": "2.0.0",
    }


@app.get("/settings")
async def settings_ui():
    return FileResponse(BASE_DIR / "static" / "settings.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=True,
    )
