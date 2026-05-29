"""
OnboardMe V2 — Settings Routes

Reads from and writes to the clients table in DB.
Single-tenant: always operates on the default client record.
"""

import io
import re
from datetime import datetime, timezone
from uuid import UUID

import httpx
import qrcode
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.services.database import (
    get_default_client,
    upsert_default_client,
    update_default_client,
    get_templates_for_client,
    upsert_template,
    get_groups_for_client,
    get_group,
    upsert_group,
    get_events_for_client,
    get_event,
    upsert_event,
    list_broadcasts,
    get_broadcast,
    get_broadcast_recipients,
)
from app.config import settings as app_settings
from app.services.journey import COMMUNITY_TOUCHPOINT_KEYS
from app.services.whatsapp import whatsapp_service
from app.services.broadcasts import (
    build_broadcast_recipients,
    create_broadcast_draft,
    generate_broadcast_message,
    parse_manual_numbers,
    queue_existing_broadcast,
)

router = APIRouter(prefix="/api", tags=["settings"])


def require_admin_token(x_admin_token: Optional[str] = Header(None)):
    if app_settings.admin_token and x_admin_token != app_settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


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
    human_escalation_whatsapp: Optional[str] = None


class ClientSettingsUpdate(BaseModel):
    community_name: Optional[str] = None
    community_description: Optional[str] = None
    agent_name: Optional[str] = None
    agent_tone: Optional[str] = None
    invite_link: Optional[str] = None
    calendly_link: Optional[str] = None
    founder_stories_link: Optional[str] = None
    operator_session_link: Optional[str] = None
    human_escalation_whatsapp: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    touchpoint_key: str
    name: Optional[str] = None
    day: Optional[int] = None
    send_time: Optional[str] = None
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
    send_time: Optional[str] = None
    phase: Optional[str] = None
    automation: Optional[bool] = None
    conditional: Optional[bool] = None
    requires_human: Optional[bool] = None
    purpose: Optional[str] = None
    cta: Optional[str] = None
    brief: Optional[str] = None
    fallback_message: Optional[str] = None
    active: Optional[bool] = None


class TemplateCreate(BaseModel):
    name: str
    day: int = 1
    send_time: Optional[str] = None
    phase: Optional[str] = "foundation"
    automation: bool = True
    conditional: bool = False
    requires_human: bool = False
    purpose: str
    cta: Optional[str] = ""
    brief: str
    fallback_message: Optional[str] = None
    active: bool = True


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str
    purpose: Optional[str] = None
    link: Optional[str] = None
    activity_day: Optional[str] = None
    cta_guidance: Optional[str] = None
    sort_order: int = 0
    active: bool = True


class GroupCreate(BaseModel):
    name: str
    description: str
    purpose: Optional[str] = None
    link: Optional[str] = None
    activity_day: Optional[str] = None
    cta_guidance: Optional[str] = None
    sort_order: int = 0
    active: bool = True


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    purpose: Optional[str] = None
    link: Optional[str] = None
    activity_day: Optional[str] = None
    cta_guidance: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


class EventResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    starts_at: str
    ends_at: Optional[str] = None
    location: Optional[str] = None
    link: Optional[str] = None
    reminder_hours_before: int = 24
    active: bool = True


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    link: Optional[str] = None
    reminder_hours_before: int = 24
    active: bool = True


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    link: Optional[str] = None
    reminder_hours_before: Optional[int] = None
    active: Optional[bool] = None


class BroadcastResponse(BaseModel):
    id: str
    title: str
    brief: Optional[str] = None
    message: str
    status: str
    recipient_source: str
    include_approved_members: bool
    member_count: int
    manual_count: int
    total_recipients: int
    created_at: Optional[str] = None
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class BroadcastRecipientResponse(BaseModel):
    id: str
    member_id: Optional[str] = None
    whatsapp: str
    source: str
    status: str
    attempts: int = 0
    last_error: Optional[str] = None
    sent_at: Optional[str] = None


class BroadcastCreate(BaseModel):
    title: str
    brief: Optional[str] = None
    message: str
    manual_numbers: Optional[str] = ""
    include_approved_members: bool = False


class BroadcastPreviewRequest(BaseModel):
    brief: str
    link: Optional[str] = None


class BroadcastPreviewResponse(BaseModel):
    message: str


class BroadcastRecipientPreviewRequest(BaseModel):
    manual_numbers: Optional[str] = ""
    include_approved_members: bool = False


class BroadcastRecipientPreviewResponse(BaseModel):
    total_recipients: int
    member_count: int
    manual_count: int
    invalid_numbers: list[str]


class LoginRequest(BaseModel):
    token: str


def _validate_send_time(send_time: Optional[str]) -> Optional[str]:
    if not send_time:
        return None
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", send_time):
        raise HTTPException(status_code=422, detail="send_time must use HH:MM format")
    return send_time


def _template_response(t: dict) -> TemplateResponse:
    return TemplateResponse(
        id=str(t["id"]),
        touchpoint_key=t["touchpoint_key"],
        name=t.get("name"),
        day=t.get("day"),
        send_time=t.get("send_time"),
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


def _group_response(g: dict) -> GroupResponse:
    return GroupResponse(
        id=str(g["id"]),
        name=g["name"],
        description=g["description"],
        purpose=g.get("purpose"),
        link=g.get("link"),
        activity_day=g.get("activity_day"),
        cta_guidance=g.get("cta_guidance"),
        sort_order=g.get("sort_order") or 0,
        active=g.get("active", True),
    )


def _event_response(e: dict) -> EventResponse:
    return EventResponse(
        id=str(e["id"]),
        title=e["title"],
        description=e.get("description"),
        starts_at=e["starts_at"],
        ends_at=e.get("ends_at"),
        location=e.get("location"),
        link=e.get("link"),
        reminder_hours_before=e.get("reminder_hours_before") or 24,
        active=e.get("active", True),
    )


def _broadcast_response(b: dict) -> BroadcastResponse:
    return BroadcastResponse(
        id=str(b["id"]),
        title=b["title"],
        brief=b.get("brief"),
        message=b["message"],
        status=b["status"],
        recipient_source=b.get("recipient_source", "manual"),
        include_approved_members=b.get("include_approved_members", False),
        member_count=b.get("member_count") or 0,
        manual_count=b.get("manual_count") or 0,
        total_recipients=b.get("total_recipients") or 0,
        created_at=b.get("created_at"),
        queued_at=b.get("queued_at"),
        started_at=b.get("started_at"),
        completed_at=b.get("completed_at"),
    )


def _broadcast_recipient_response(r: dict) -> BroadcastRecipientResponse:
    return BroadcastRecipientResponse(
        id=str(r["id"]),
        member_id=str(r["member_id"]) if r.get("member_id") else None,
        whatsapp=r["whatsapp"],
        source=r.get("source", "manual"),
        status=r.get("status", "pending"),
        attempts=r.get("attempts") or 0,
        last_error=r.get("last_error"),
        sent_at=r.get("sent_at"),
    )


def _ensure_aware(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ═══════════════════════════════════════════════════════════
# Client Settings
# ═══════════════════════════════════════════════════════════


@router.post("/admin/login")
async def login_admin(payload: LoginRequest):
    """Validate admin token. The dependency checks X-Admin-Token for API calls."""
    if app_settings.admin_token and payload.token != app_settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return {"status": "ok"}


@router.get("/settings", response_model=ClientSettingsResponse, dependencies=[Depends(require_admin_token)])
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
        human_escalation_whatsapp=client.get("human_escalation_whatsapp") or app_settings.human_escalation_whatsapp,
    )


@router.put("/settings", response_model=ClientSettingsResponse, dependencies=[Depends(require_admin_token)])
async def update_settings(updates: ClientSettingsUpdate):
    """Update client/community settings. Changes take effect immediately."""
    current = await get_default_client()
    if not current:
        current = await upsert_default_client()

    client_updates = updates.model_dump(exclude_unset=True)
    client = await update_default_client(**client_updates) if client_updates else current

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
        human_escalation_whatsapp=client.get("human_escalation_whatsapp") or app_settings.human_escalation_whatsapp,
    )


# ═══════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════


@router.get("/templates", response_model=list[TemplateResponse], dependencies=[Depends(require_admin_token)])
async def list_templates():
    """Get all templates for the default client."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    templates = await get_templates_for_client(client["id"], include_inactive=True)
    templates = [t for t in templates if t["touchpoint_key"] in COMMUNITY_TOUCHPOINT_KEYS]
    return [_template_response(t) for t in templates]


@router.post("/templates", response_model=TemplateResponse, dependencies=[Depends(require_admin_token)])
async def create_template(payload: TemplateCreate):
    """Create a new automated message template for future member journeys."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    key_base = re.sub(r"[^a-z0-9]+", "_", payload.name.lower()).strip("_") or "message"
    touchpoint_key = f"custom_{int(datetime.now(timezone.utc).timestamp())}_{key_base[:32]}"

    result = await upsert_template(
        client_id=client["id"],
        touchpoint_key=touchpoint_key,
        name=payload.name,
        day=payload.day,
        send_time=_validate_send_time(payload.send_time),
        phase=payload.phase,
        automation=payload.automation,
        conditional=payload.conditional,
        requires_human=payload.requires_human,
        purpose=payload.purpose,
        cta=payload.cta or "",
        brief=payload.brief,
        fallback_message=payload.fallback_message,
        active=payload.active,
    )

    return _template_response(result)


@router.put("/templates/{touchpoint_key}", response_model=TemplateResponse, dependencies=[Depends(require_admin_token)])
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
        send_time=_validate_send_time(updates.send_time if updates.send_time is not None else existing.get("send_time")),
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

    return _template_response(result)


# ═══════════════════════════════════════════════════════════
# Community Groups
# ═══════════════════════════════════════════════════════════


@router.get("/groups", response_model=list[GroupResponse], dependencies=[Depends(require_admin_token)])
async def list_groups():
    """Get all configured MBN community groups."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    groups = await get_groups_for_client(client["id"], include_inactive=True)
    return [_group_response(g) for g in groups]


@router.post("/groups", response_model=GroupResponse, dependencies=[Depends(require_admin_token)])
async def create_group(payload: GroupCreate):
    """Create a community group used as AI routing context."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    result = await upsert_group(
        client_id=client["id"],
        name=payload.name.strip(),
        description=payload.description.strip(),
        purpose=payload.purpose,
        link=payload.link,
        activity_day=payload.activity_day,
        cta_guidance=payload.cta_guidance,
        sort_order=payload.sort_order,
        active=payload.active,
    )
    return _group_response(result)


@router.put("/groups/{group_id}", response_model=GroupResponse, dependencies=[Depends(require_admin_token)])
async def update_group(group_id: UUID, updates: GroupUpdate):
    """Update a community group."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    existing = await get_group(group_id)
    if not existing or existing["client_id"] != client["id"]:
        raise HTTPException(status_code=404, detail="Group not found")

    result = await upsert_group(
        client_id=client["id"],
        group_id=group_id,
        name=(updates.name if updates.name is not None else existing["name"]).strip(),
        description=(updates.description if updates.description is not None else existing["description"]).strip(),
        purpose=updates.purpose if updates.purpose is not None else existing.get("purpose"),
        link=updates.link if updates.link is not None else existing.get("link"),
        activity_day=updates.activity_day if updates.activity_day is not None else existing.get("activity_day"),
        cta_guidance=updates.cta_guidance if updates.cta_guidance is not None else existing.get("cta_guidance"),
        sort_order=updates.sort_order if updates.sort_order is not None else existing.get("sort_order", 0),
        active=updates.active if updates.active is not None else existing.get("active", True),
    )
    return _group_response(result)


# ═══════════════════════════════════════════════════════════
# Community Events
# ═══════════════════════════════════════════════════════════


@router.get("/events", response_model=list[EventResponse], dependencies=[Depends(require_admin_token)])
async def list_events():
    """Get all configured community events."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    events = await get_events_for_client(client["id"], include_inactive=True)
    return [_event_response(e) for e in events]


@router.post("/events", response_model=EventResponse, dependencies=[Depends(require_admin_token)])
async def create_event(payload: EventCreate):
    """Create a community event used as AI and reminder context."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    if payload.reminder_hours_before < 0:
        raise HTTPException(status_code=422, detail="reminder_hours_before must be 0 or greater")

    result = await upsert_event(
        client_id=client["id"],
        title=payload.title.strip(),
        description=payload.description,
        starts_at=_ensure_aware(payload.starts_at),
        ends_at=_ensure_aware(payload.ends_at),
        location=payload.location,
        link=payload.link,
        reminder_hours_before=payload.reminder_hours_before,
        active=payload.active,
    )
    return _event_response(result)


@router.put("/events/{event_id}", response_model=EventResponse, dependencies=[Depends(require_admin_token)])
async def update_event(event_id: UUID, updates: EventUpdate):
    """Update a community event."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")

    existing = await get_event(event_id)
    if not existing or existing["client_id"] != client["id"]:
        raise HTTPException(status_code=404, detail="Event not found")

    reminder_hours_before = (
        updates.reminder_hours_before
        if updates.reminder_hours_before is not None
        else existing.get("reminder_hours_before", 24)
    )
    if reminder_hours_before < 0:
        raise HTTPException(status_code=422, detail="reminder_hours_before must be 0 or greater")

    result = await upsert_event(
        client_id=client["id"],
        event_id=event_id,
        title=(updates.title if updates.title is not None else existing["title"]).strip(),
        description=updates.description if updates.description is not None else existing.get("description"),
        starts_at=_ensure_aware(updates.starts_at) if updates.starts_at is not None else _ensure_aware(datetime.fromisoformat(existing["starts_at"])),
        ends_at=_ensure_aware(updates.ends_at) if updates.ends_at is not None else (_ensure_aware(datetime.fromisoformat(existing["ends_at"])) if existing.get("ends_at") else None),
        location=updates.location if updates.location is not None else existing.get("location"),
        link=updates.link if updates.link is not None else existing.get("link"),
        reminder_hours_before=reminder_hours_before,
        active=updates.active if updates.active is not None else existing.get("active", True),
    )
    return _event_response(result)


# ═══════════════════════════════════════════════════════════
# Broadcasts
# ═══════════════════════════════════════════════════════════


@router.get("/broadcasts", response_model=list[BroadcastResponse], dependencies=[Depends(require_admin_token)])
async def list_broadcast_records():
    """List recent manual broadcasts."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    broadcasts = await list_broadcasts(client["id"])
    return [_broadcast_response(b) for b in broadcasts]


@router.get("/broadcasts/{broadcast_id}", dependencies=[Depends(require_admin_token)])
async def get_broadcast_record(broadcast_id: UUID):
    """Get one broadcast and its recipients."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    broadcast = await get_broadcast(broadcast_id)
    if not broadcast or broadcast["client_id"] != client["id"]:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    recipients = await get_broadcast_recipients(broadcast_id, limit=250)
    return {
        "broadcast": _broadcast_response(broadcast),
        "recipients": [_broadcast_recipient_response(r) for r in recipients],
    }


@router.post("/broadcasts/preview", response_model=BroadcastPreviewResponse, dependencies=[Depends(require_admin_token)])
async def preview_broadcast(payload: BroadcastPreviewRequest):
    """Generate a WhatsApp broadcast preview from an admin brief."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    if not payload.brief.strip():
        raise HTTPException(status_code=422, detail="Brief is required")
    message = generate_broadcast_message(client, payload.brief, payload.link)
    return BroadcastPreviewResponse(message=message)


@router.post("/broadcasts/recipients/preview", response_model=BroadcastRecipientPreviewResponse, dependencies=[Depends(require_admin_token)])
async def preview_broadcast_recipients(payload: BroadcastRecipientPreviewRequest):
    """Preview recipient counts without creating a broadcast."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    manual_numbers, invalid_numbers = parse_manual_numbers(payload.manual_numbers or "")
    from app.services.database import get_approved_members
    approved_members = await get_approved_members(client["id"]) if payload.include_approved_members else []
    recipients = build_broadcast_recipients(approved_members, manual_numbers, payload.include_approved_members)
    member_count = sum(1 for r in recipients if r.get("source") == "member")
    manual_count = sum(1 for r in recipients if r.get("source") == "manual")
    return BroadcastRecipientPreviewResponse(
        total_recipients=len(recipients),
        member_count=member_count,
        manual_count=manual_count,
        invalid_numbers=invalid_numbers,
    )


@router.post("/broadcasts", response_model=BroadcastResponse, dependencies=[Depends(require_admin_token)])
async def create_broadcast_record(payload: BroadcastCreate):
    """Create a manual broadcast draft and recipient rows."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message is required")

    try:
        broadcast = await create_broadcast_draft(
            client_data=client,
            title=payload.title.strip(),
            message=payload.message.strip(),
            brief=payload.brief.strip() if payload.brief else None,
            manual_numbers_raw=payload.manual_numbers or "",
            include_approved_members=payload.include_approved_members,
        )
        return _broadcast_response(broadcast)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/broadcasts/{broadcast_id}/send", response_model=BroadcastResponse, dependencies=[Depends(require_admin_token)])
async def send_broadcast_record(broadcast_id: UUID):
    """Queue a draft broadcast for rate-limited sending."""
    client = await get_default_client()
    if not client:
        raise HTTPException(status_code=404, detail="No client configured")
    broadcast = await get_broadcast(broadcast_id)
    if not broadcast or broadcast["client_id"] != client["id"]:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if broadcast["status"] not in {"draft", "failed"}:
        raise HTTPException(status_code=409, detail="Broadcast is already queued or sent")

    queued = await queue_existing_broadcast(broadcast_id)
    if not queued:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return _broadcast_response(queued)


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


@router.get("/settings/timing", response_model=TimingConfigResponse, dependencies=[Depends(require_admin_token)])
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


@router.get("/whatsapp/status", dependencies=[Depends(require_admin_token)])
async def get_whatsapp_status():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{app_settings.whatsapp_bridge_url}/health")
        response.raise_for_status()
        return response.json()


@router.get("/whatsapp/qr", dependencies=[Depends(require_admin_token)])
async def get_whatsapp_qr():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{app_settings.whatsapp_bridge_url}/qr")
        response.raise_for_status()
        return response.json()


@router.get("/whatsapp/qr.png", dependencies=[Depends(require_admin_token)])
async def get_whatsapp_qr_image():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{app_settings.whatsapp_bridge_url}/qr")
        response.raise_for_status()
        data = response.json()

    qr_value = data.get("qr")
    if not qr_value:
        raise HTTPException(status_code=404, detail=data.get("message", "QR code not available"))

    image = qrcode.make(qr_value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/whatsapp/disconnect", dependencies=[Depends(require_admin_token)])
async def disconnect_whatsapp():
    return await whatsapp_service.disconnect()
