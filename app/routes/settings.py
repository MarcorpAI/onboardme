"""
OnboardMe V2 — Settings Routes

Reads from and writes to the clients table in DB.
Single-tenant: always operates on the default client record.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.database import (
    get_default_client,
    upsert_default_client,
    get_templates_for_client,
    upsert_template,
)
from app.config import settings as app_settings

router = APIRouter(prefix="/api", tags=["settings"])


# ═══════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════


class ClientSettingsResponse(BaseModel):
    client_name: str
    community_name: str
    community_description: Optional[str] = None
    agent_name: str
    agent_tone: str
    webhook_secret: str
    invite_link: Optional[str] = None
    calendly_link: Optional[str] = None
    founder_stories_link: Optional[str] = None
    operator_session_link: Optional[str] = None


class ClientSettingsUpdate(BaseModel):
    community_name: Optional[str] = None
    community_description: Optional[str] = None
    agent_name: Optional[str] = None
    agent_tone: Optional[str] = None
    invite_link: Optional[str] = None
    calendly_link: Optional[str] = None
    founder_stories_link: Optional[str] = None
    operator_session_link: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    touchpoint_key: str
    name: Optional[str] = None
    day: Optional[int] = None
    phase: Optional[str] = None
    automation: bool = True
    conditional: bool = False
    requires_human: bool = False
    purpose: str
    cta: str
    brief: str
    fallback_message: Optional[str] = None
    active: bool


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    day: Optional[int] = None
    phase: Optional[str] = None
    automation: Optional[bool] = None
    conditional: Optional[bool] = None
    requires_human: Optional[bool] = None
    purpose: Optional[str] = None
    cta: Optional[str] = None
    brief: Optional[str] = None
    fallback_message: Optional[str] = None
    active: Optional[bool] = None


# ═══════════════════════════════════════════════════════════
# Client Settings
# ═══════════════════════════════════════════════════════════


@router.get("/settings", response_model=ClientSettingsResponse)
async def get_settings():
    """Get the current client/community settings."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    return ClientSettingsResponse(
        client_name=client.get("name", app_settings.client_name),
        community_name=client.get("community_name", app_settings.community_name),
        community_description=client.get("community_description", app_settings.community_description),
        agent_name=client.get("agent_name", app_settings.agent_name),
        agent_tone=client.get("agent_tone", app_settings.agent_tone),
        webhook_secret=client.get("webhook_secret", app_settings.webhook_secret),
        invite_link=client.get("invite_link", app_settings.invite_link),
        calendly_link=client.get("calendly_link", app_settings.calendly_link),
        founder_stories_link=client.get("founder_stories_link", app_settings.founder_stories_link),
        operator_session_link=client.get("operator_session_link", app_settings.operator_session_link),
    )


@router.put("/settings", response_model=ClientSettingsResponse)
async def update_settings(updates: ClientSettingsUpdate):
    """Update client/community settings. Changes take effect immediately."""
    from app.config import settings as cfg

    # Merge updates with existing env defaults for fields not in DB
    current = await get_default_client()
    if not current:
        # Create default client from env vars if it doesn't exist
        current = await upsert_default_client()

    # We need to update the client in the DB
    # The simplest way: update env-backed defaults via upsert
    # But we want DB-stored overrides to persist
    # Temporarily patch settings for the upsert
    if updates.community_name is not None:
        cfg.community_name = updates.community_name
    if updates.community_description is not None:
        cfg.community_description = updates.community_description
    if updates.agent_name is not None:
        cfg.agent_name = updates.agent_name
    if updates.agent_tone is not None:
        cfg.agent_tone = updates.agent_tone
    if updates.invite_link is not None:
        cfg.invite_link = updates.invite_link
    if updates.calendly_link is not None:
        cfg.calendly_link = updates.calendly_link
    if updates.founder_stories_link is not None:
        cfg.founder_stories_link = updates.founder_stories_link
    if updates.operator_session_link is not None:
        cfg.operator_session_link = updates.operator_session_link

    client = await upsert_default_client()

    return ClientSettingsResponse(
        client_name=client.get("name", cfg.client_name),
        community_name=client.get("community_name", cfg.community_name),
        community_description=client.get("community_description", cfg.community_description),
        agent_name=client.get("agent_name", cfg.agent_name),
        agent_tone=client.get("agent_tone", cfg.agent_tone),
        webhook_secret=client.get("webhook_secret", cfg.webhook_secret),
        invite_link=client.get("invite_link", cfg.invite_link),
        calendly_link=client.get("calendly_link", cfg.calendly_link),
        founder_stories_link=client.get("founder_stories_link", cfg.founder_stories_link),
        operator_session_link=client.get("operator_session_link", cfg.operator_session_link),
    )


# ═══════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates():
    """Get all templates for the default client."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    templates = await get_templates_for_client(client["id"], include_inactive=True)
    return [
        TemplateResponse(
            id=str(t["id"]),
            touchpoint_key=t["touchpoint_key"],
            name=t.get("name"),
            day=t.get("day"),
            phase=t.get("phase"),
            automation=t.get("automation", True),
            conditional=t.get("conditional", False),
            requires_human=t.get("requires_human", False),
            purpose=t["purpose"],
            cta=t["cta"],
            brief=t["brief"],
            fallback_message=t.get("fallback_message"),
            active=t["active"],
        )
        for t in templates
    ]


@router.put("/templates/{touchpoint_key}", response_model=TemplateResponse)
async def update_template(touchpoint_key: str, updates: TemplateUpdate):
    """Update a specific template by touchpoint_key."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    # Get existing template to merge updates
    existing = None
    templates = await get_templates_for_client(client["id"], include_inactive=True)
    for t in templates:
        if t["touchpoint_key"] == touchpoint_key:
            existing = t
            break

    if not existing:
        raise HTTPException(status_code=404, detail=f"Template '{touchpoint_key}' not found")

    result = await upsert_template(
        client_id=client["id"],
        touchpoint_key=touchpoint_key,
        name=updates.name if updates.name is not None else existing.get("name"),
        day=updates.day if updates.day is not None else existing.get("day"),
        phase=updates.phase if updates.phase is not None else existing.get("phase"),
        automation=updates.automation if updates.automation is not None else existing.get("automation", True),
        conditional=updates.conditional if updates.conditional is not None else existing.get("conditional", False),
        requires_human=updates.requires_human if updates.requires_human is not None else existing.get("requires_human", False),
        purpose=updates.purpose if updates.purpose is not None else existing["purpose"],
        cta=updates.cta if updates.cta is not None else existing["cta"],
        brief=updates.brief if updates.brief is not None else existing["brief"],
        fallback_message=updates.fallback_message if updates.fallback_message is not None else existing.get("fallback_message"),
        active=updates.active if updates.active is not None else existing["active"],
    )

    return TemplateResponse(
        id=str(result["id"]),
        touchpoint_key=result["touchpoint_key"],
        name=result.get("name"),
        day=result.get("day"),
        phase=result.get("phase"),
        automation=result.get("automation", True),
        conditional=result.get("conditional", False),
        requires_human=result.get("requires_human", False),
        purpose=result["purpose"],
        cta=result["cta"],
        brief=result["brief"],
        fallback_message=result.get("fallback_message"),
        active=result["active"],
    )


# ═══════════════════════════════════════════════════════════
# Timing Configuration
# ═══════════════════════════════════════════════════════════


class TimingConfigResponse(BaseModel):
    follow_up_delay_mins: int
    abandon_after_hours: int
    nudge_delay_mins: int
    timeout_hours: int
    engagement_threshold: float
    engagement_days: int


@router.get("/settings/timing", response_model=TimingConfigResponse)
async def get_timing_settings():
    """Get timing configuration (from env vars, not stored in DB)."""
    return TimingConfigResponse(
        follow_up_delay_mins=app_settings.follow_up_delay_mins,
        abandon_after_hours=app_settings.abandon_after_hours,
        nudge_delay_mins=app_settings.nudge_delay_mins,
        timeout_hours=app_settings.timeout_hours,
        engagement_threshold=app_settings.engagement_threshold,
        engagement_days=app_settings.engagement_days,
    )
