"""
OnboardMe V2 — Database Service
All async SQLAlchemy 2.0 queries across 6 tables:
clients, members, conversations, messages, journey_touchpoints, templates
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, and_, or_, func, text
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import uuid
import logging

from app.config import DATABASE_CONNECT_ARGS, DATABASE_URL, settings
from app.models.base import Base
from app.models.client import Client
from app.models.member import Member
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.touchpoint import JourneyTouchpoint
from app.models.template import Template
from app.models.community_group import CommunityGroup
from app.models.community_event import CommunityEvent
from app.models.broadcast import Broadcast, BroadcastRecipient

logger = logging.getLogger(__name__)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=DATABASE_CONNECT_ARGS,
    pool_pre_ping=True,
    pool_recycle=1800,
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _member_to_dict(m: Member) -> Dict[str, Any]:
    return {
        "id": m.id,
        "client_id": m.client_id,
        "name": m.name,
        "whatsapp": m.whatsapp,
        "whatsapp_lid": m.whatsapp_lid,
        "email": m.email,
        "industry": m.industry,
        "company": m.company,
        "stage": m.stage,
        "building": m.building,
        "focus_areas": m.focus_areas,
        "why_community": m.why_community,
        "goals": m.goals,
        "revenue_range": m.revenue_range,
        "approved_at": m.approved_at.isoformat() if m.approved_at else None,
        "approval_source": m.approval_source,
        "journey_day": m.journey_day,
        "journey_phase": m.journey_phase,
        "engagement_score": m.engagement_score,
        "state": m.state,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "last_active_at": m.last_active_at.isoformat() if m.last_active_at else None,
    }


def _client_to_dict(c: Client) -> Dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "community_name": c.community_name,
        "community_description": c.community_description,
        "agent_name": c.agent_name,
        "agent_tone": c.agent_tone,
        "webhook_secret": c.webhook_secret,
        "invite_link": c.invite_link,
        "calendly_link": c.calendly_link,
        "founder_stories_link": c.founder_stories_link,
        "operator_session_link": c.operator_session_link,
        "human_escalation_whatsapp": c.human_escalation_whatsapp,
    }


def _conversation_to_dict(c: Conversation) -> Dict[str, Any]:
    return {
        "id": c.id,
        "member_id": c.member_id,
        "touchpoint_key": c.touchpoint_key,
        "opened_at": c.opened_at.isoformat() if c.opened_at else None,
        "closed_at": c.closed_at.isoformat() if c.closed_at else None,
        "state": c.state,
    }


def _touchpoint_to_dict(t: JourneyTouchpoint) -> Dict[str, Any]:
    return {
        "id": t.id,
        "member_id": t.member_id,
        "touchpoint_key": t.touchpoint_key,
        "scheduled_for": t.scheduled_for.isoformat() if t.scheduled_for else None,
        "fired_at": t.fired_at.isoformat() if t.fired_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "state": t.state,
        "conversation_id": t.conversation_id,
        "requires_human": t.requires_human,
        "nudge_sent": t.nudge_sent,
    }


def _template_to_dict(t: Template) -> Dict[str, Any]:
    return {
        "id": t.id,
        "client_id": t.client_id,
        "touchpoint_key": t.touchpoint_key,
        "name": t.name,
        "day": t.day,
        "send_time": t.send_time,
        "phase": t.phase,
        "automation": t.automation,
        "conditional": t.conditional,
        "requires_human": t.requires_human,
        "purpose": t.purpose,
        "cta": t.cta,
        "brief": t.brief,
        "fallback_message": t.fallback_message,
        "active": t.active,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _community_group_to_dict(g: CommunityGroup) -> Dict[str, Any]:
    return {
        "id": g.id,
        "client_id": g.client_id,
        "name": g.name,
        "description": g.description,
        "purpose": g.purpose,
        "link": g.link,
        "activity_day": g.activity_day,
        "cta_guidance": g.cta_guidance,
        "sort_order": g.sort_order,
        "active": g.active,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


def _community_event_to_dict(e: CommunityEvent) -> Dict[str, Any]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "title": e.title,
        "description": e.description,
        "starts_at": e.starts_at.isoformat() if e.starts_at else None,
        "ends_at": e.ends_at.isoformat() if e.ends_at else None,
        "location": e.location,
        "link": e.link,
        "reminder_hours_before": e.reminder_hours_before,
        "active": e.active,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _broadcast_to_dict(b: Broadcast) -> Dict[str, Any]:
    return {
        "id": b.id,
        "client_id": b.client_id,
        "title": b.title,
        "brief": b.brief,
        "message": b.message,
        "status": b.status,
        "recipient_source": b.recipient_source,
        "include_approved_members": b.include_approved_members,
        "member_count": b.member_count,
        "manual_count": b.manual_count,
        "total_recipients": b.total_recipients,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "queued_at": b.queued_at.isoformat() if b.queued_at else None,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _broadcast_recipient_to_dict(r: BroadcastRecipient) -> Dict[str, Any]:
    return {
        "id": r.id,
        "broadcast_id": r.broadcast_id,
        "member_id": r.member_id,
        "whatsapp": r.whatsapp,
        "source": r.source,
        "status": r.status,
        "attempts": r.attempts,
        "last_error": r.last_error,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ═══════════════════════════════════════════════════════════
# Initialisation
# ═══════════════════════════════════════════════════════════

async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS name TEXT"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS day INTEGER"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS send_time TEXT"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS phase TEXT"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS automation BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS conditional BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS requires_human BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS human_escalation_whatsapp TEXT"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS community_groups (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                purpose TEXT,
                link TEXT,
                activity_day TEXT,
                cta_guidance TEXT,
                sort_order INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_community_groups_client_id ON community_groups(client_id)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS community_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ,
                location TEXT,
                link TEXT,
                reminder_hours_before INTEGER DEFAULT 24,
                active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_community_events_client_id ON community_events(client_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_community_events_starts_at ON community_events(starts_at)"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                brief TEXT,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                recipient_source TEXT DEFAULT 'manual',
                include_approved_members BOOLEAN DEFAULT FALSE,
                member_count INTEGER DEFAULT 0,
                manual_count INTEGER DEFAULT 0,
                total_recipients INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                queued_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS broadcast_recipients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broadcast_id UUID NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
                member_id UUID REFERENCES members(id) ON DELETE SET NULL,
                whatsapp TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_broadcasts_client_id ON broadcasts(client_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_broadcast_id ON broadcast_recipients(broadcast_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_status ON broadcast_recipients(status)"))
    logger.info("Database tables initialised")


async def get_default_client() -> Optional[Dict[str, Any]]:
    """Get the single default client record (V2 is single-tenant)."""
    async with async_session_maker() as db:
        stmt = select(Client).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()
        if client:
            return _client_to_dict(client)
        return None


async def upsert_default_client() -> Dict[str, Any]:
    """
    Create the default client from env settings if one does not exist.
    Returns the client dict.
    """
    async with async_session_maker() as db:
        stmt = select(Client).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()

        if client:
            logger.info(f"Default client loaded: {client.id} ({client.community_name})")
            return _client_to_dict(client)
        else:
            client = Client(
                name=settings.client_name,
                community_name=settings.community_name,
                community_description=settings.community_description,
                agent_name=settings.agent_name,
                agent_tone=settings.agent_tone,
                webhook_secret=settings.webhook_secret,
                invite_link=settings.invite_link,
                calendly_link=settings.calendly_link,
                founder_stories_link=settings.founder_stories_link,
                operator_session_link=settings.operator_session_link,
                human_escalation_whatsapp=settings.human_escalation_whatsapp,
            )
            db.add(client)

        await db.commit()
        await db.refresh(client)
        logger.info(f"Default client created: {client.id} ({client.community_name})")
        return _client_to_dict(client)


async def update_default_client(**updates) -> Dict[str, Any]:
    """Update DB-backed default client settings without falling back to env values."""
    async with async_session_maker() as db:
        stmt = select(Client).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()

        if not client:
            client = Client(
                name=settings.client_name,
                community_name=settings.community_name,
                community_description=settings.community_description,
                agent_name=settings.agent_name,
                agent_tone=settings.agent_tone,
                webhook_secret=settings.webhook_secret,
                invite_link=settings.invite_link,
                calendly_link=settings.calendly_link,
                founder_stories_link=settings.founder_stories_link,
                operator_session_link=settings.operator_session_link,
                human_escalation_whatsapp=settings.human_escalation_whatsapp,
            )
            db.add(client)
        else:
            for key, value in updates.items():
                if value is not None and hasattr(client, key):
                    setattr(client, key, value)

        await db.commit()
        await db.refresh(client)
        logger.info(f"Default client updated: {client.id} ({client.community_name})")
        return _client_to_dict(client)


async def sync_default_client_from_env() -> Dict[str, Any]:
    """Force-sync the default client from env settings."""
    async with async_session_maker() as db:
        stmt = select(Client).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()

        if not client:
            client = Client(
                name=settings.client_name,
                community_name=settings.community_name,
                community_description=settings.community_description,
                agent_name=settings.agent_name,
                agent_tone=settings.agent_tone,
                webhook_secret=settings.webhook_secret,
                invite_link=settings.invite_link,
                calendly_link=settings.calendly_link,
                founder_stories_link=settings.founder_stories_link,
                operator_session_link=settings.operator_session_link,
                human_escalation_whatsapp=settings.human_escalation_whatsapp,
            )
            db.add(client)
        else:
            client.name = settings.client_name
            client.community_name = settings.community_name
            client.community_description = settings.community_description
            client.agent_name = settings.agent_name
            client.agent_tone = settings.agent_tone
            client.webhook_secret = settings.webhook_secret
            client.invite_link = settings.invite_link
            client.calendly_link = settings.calendly_link
            client.founder_stories_link = settings.founder_stories_link
            client.operator_session_link = settings.operator_session_link
            client.human_escalation_whatsapp = settings.human_escalation_whatsapp

        await db.commit()
        await db.refresh(client)
        logger.info(f"Default client force-synced from env: {client.id} ({client.community_name})")
        return _client_to_dict(client)


async def get_client_by_secret(secret: str) -> Optional[Dict[str, Any]]:
    """Verify a webhook secret and return the matching client."""
    async with async_session_maker() as db:
        stmt = select(Client).where(Client.webhook_secret == secret).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()
        if client:
            return _client_to_dict(client)
        return None


# ═══════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════

async def get_templates_for_client(client_id: uuid.UUID, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get templates for a client."""
    async with async_session_maker() as db:
        filters = [Template.client_id == client_id]
        if not include_inactive:
            filters.append(Template.active == True)
        stmt = select(Template).where(and_(*filters)).order_by(Template.day.asc(), Template.touchpoint_key.asc())
        result = await db.execute(stmt)
        templates = result.scalars().all()
        return [_template_to_dict(t) for t in templates]


async def get_template(client_id: uuid.UUID, touchpoint_key: str) -> Optional[Dict[str, Any]]:
    """Get a specific template for a client."""
    async with async_session_maker() as db:
        stmt = select(Template).where(
            and_(Template.client_id == client_id, Template.touchpoint_key == touchpoint_key)
        ).limit(1)
        result = await db.execute(stmt)
        t = result.scalar_one_or_none()
        if t:
            return _template_to_dict(t)
        return None


async def upsert_template(client_id: uuid.UUID, touchpoint_key: str, purpose: str,
                          cta: str, brief: str, fallback_message: Optional[str] = None,
                          active: bool = True, name: Optional[str] = None,
                          day: Optional[int] = None, send_time: Optional[str] = None,
                          phase: Optional[str] = None,
                          automation: bool = True, conditional: bool = False,
                          requires_human: bool = False) -> Dict[str, Any]:
    """Create or update a template."""
    async with async_session_maker() as db:
        stmt = select(Template).where(
            and_(Template.client_id == client_id, Template.touchpoint_key == touchpoint_key)
        ).limit(1)
        result = await db.execute(stmt)
        t = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if t:
            t.name = name
            t.day = day
            t.send_time = send_time
            t.phase = phase
            t.automation = automation
            t.conditional = conditional
            t.requires_human = requires_human
            t.purpose = purpose
            t.cta = cta
            t.brief = brief
            t.fallback_message = fallback_message
            t.active = active
            t.updated_at = now
        else:
            t = Template(
                client_id=client_id,
                touchpoint_key=touchpoint_key,
                name=name,
                day=day,
                send_time=send_time,
                phase=phase,
                automation=automation,
                conditional=conditional,
                requires_human=requires_human,
                purpose=purpose,
                cta=cta,
                brief=brief,
                fallback_message=fallback_message,
                active=active,
                updated_at=now,
            )
            db.add(t)

        await db.commit()
        await db.refresh(t)
        return _template_to_dict(t)


async def delete_templates_for_client(client_id: uuid.UUID) -> int:
    """Delete all templates for a client. Intended for explicit admin resets."""
    async with async_session_maker() as db:
        stmt = select(Template).where(Template.client_id == client_id)
        result = await db.execute(stmt)
        templates = result.scalars().all()
        count = len(templates)
        for template in templates:
            await db.delete(template)
        await db.commit()
        return count


async def sync_template_metadata(client_id: uuid.UUID, touchpoint_key: str, **metadata):
    """Update schedule metadata without overwriting editable message copy."""
    async with async_session_maker() as db:
        stmt = select(Template).where(
            and_(Template.client_id == client_id, Template.touchpoint_key == touchpoint_key)
        ).limit(1)
        result = await db.execute(stmt)
        t = result.scalar_one_or_none()
        if not t:
            return

        for key, value in metadata.items():
            if hasattr(t, key):
                if key == "day" and getattr(t, key) is not None:
                    continue
                setattr(t, key, value)
        t.updated_at = datetime.now(timezone.utc)
        await db.commit()


# ═══════════════════════════════════════════════════════════
# Community Groups
# ═══════════════════════════════════════════════════════════

async def get_groups_for_client(client_id: uuid.UUID, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get configured community groups for a client."""
    async with async_session_maker() as db:
        filters = [CommunityGroup.client_id == client_id]
        if not include_inactive:
            filters.append(CommunityGroup.active == True)
        stmt = select(CommunityGroup).where(and_(*filters)).order_by(
            CommunityGroup.sort_order.asc(), CommunityGroup.name.asc()
        )
        result = await db.execute(stmt)
        groups = result.scalars().all()
        return [_community_group_to_dict(g) for g in groups]


async def get_group(group_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get one community group by ID."""
    async with async_session_maker() as db:
        result = await db.get(CommunityGroup, group_id)
        return _community_group_to_dict(result) if result else None


async def upsert_group(
    client_id: uuid.UUID,
    name: str,
    description: str,
    group_id: Optional[uuid.UUID] = None,
    purpose: Optional[str] = None,
    link: Optional[str] = None,
    activity_day: Optional[str] = None,
    cta_guidance: Optional[str] = None,
    sort_order: int = 0,
    active: bool = True,
) -> Dict[str, Any]:
    """Create or update a community group."""
    async with async_session_maker() as db:
        group = None
        if group_id:
            group = await db.get(CommunityGroup, group_id)

        if not group:
            stmt = select(CommunityGroup).where(
                and_(CommunityGroup.client_id == client_id, CommunityGroup.name == name)
            ).limit(1)
            result = await db.execute(stmt)
            group = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if group:
            group.name = name
            group.description = description
            group.purpose = purpose
            group.link = link
            group.activity_day = activity_day
            group.cta_guidance = cta_guidance
            group.sort_order = sort_order
            group.active = active
            group.updated_at = now
        else:
            group = CommunityGroup(
                client_id=client_id,
                name=name,
                description=description,
                purpose=purpose,
                link=link,
                activity_day=activity_day,
                cta_guidance=cta_guidance,
                sort_order=sort_order,
                active=active,
                updated_at=now,
            )
            db.add(group)

        await db.commit()
        await db.refresh(group)
        return _community_group_to_dict(group)


# ═══════════════════════════════════════════════════════════
# Community Events
# ═══════════════════════════════════════════════════════════

async def get_events_for_client(
    client_id: uuid.UUID,
    include_inactive: bool = False,
    upcoming_only: bool = False,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Get configured community events for a client."""
    async with async_session_maker() as db:
        filters = [CommunityEvent.client_id == client_id]
        if not include_inactive:
            filters.append(CommunityEvent.active == True)
        if upcoming_only:
            filters.append(CommunityEvent.starts_at >= (now or datetime.now(timezone.utc)))
        stmt = select(CommunityEvent).where(and_(*filters)).order_by(CommunityEvent.starts_at.asc())
        result = await db.execute(stmt)
        events = result.scalars().all()
        return [_community_event_to_dict(e) for e in events]


async def get_event(event_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get one community event by ID."""
    async with async_session_maker() as db:
        result = await db.get(CommunityEvent, event_id)
        return _community_event_to_dict(result) if result else None


async def get_upcoming_events_for_client(
    client_id: uuid.UUID,
    limit: int = 5,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Get active upcoming events to provide as AI context."""
    async with async_session_maker() as db:
        stmt = (
            select(CommunityEvent)
            .where(
                and_(
                    CommunityEvent.client_id == client_id,
                    CommunityEvent.active == True,
                    CommunityEvent.starts_at >= (now or datetime.now(timezone.utc)),
                )
            )
            .order_by(CommunityEvent.starts_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        events = result.scalars().all()
        return [_community_event_to_dict(e) for e in events]


async def get_events_due_for_reminders(
    client_id: uuid.UUID,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Get active upcoming events whose reminder window has opened."""
    now = now or datetime.now(timezone.utc)
    async with async_session_maker() as db:
        reminder_at = CommunityEvent.starts_at - func.make_interval(0, 0, 0, 0, CommunityEvent.reminder_hours_before)
        stmt = (
            select(CommunityEvent)
            .where(
                and_(
                    CommunityEvent.client_id == client_id,
                    CommunityEvent.active == True,
                    CommunityEvent.starts_at > now,
                    reminder_at <= now,
                )
            )
            .order_by(CommunityEvent.starts_at.asc())
        )
        result = await db.execute(stmt)
        events = result.scalars().all()
        return [_community_event_to_dict(e) for e in events]


async def upsert_event(
    client_id: uuid.UUID,
    title: str,
    starts_at: datetime,
    event_id: Optional[uuid.UUID] = None,
    description: Optional[str] = None,
    ends_at: Optional[datetime] = None,
    location: Optional[str] = None,
    link: Optional[str] = None,
    reminder_hours_before: int = 24,
    active: bool = True,
) -> Dict[str, Any]:
    """Create or update a community event."""
    async with async_session_maker() as db:
        event = await db.get(CommunityEvent, event_id) if event_id else None

        now = datetime.now(timezone.utc)
        if event:
            event.title = title
            event.description = description
            event.starts_at = starts_at
            event.ends_at = ends_at
            event.location = location
            event.link = link
            event.reminder_hours_before = reminder_hours_before
            event.active = active
            event.updated_at = now
        else:
            event = CommunityEvent(
                client_id=client_id,
                title=title,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
                location=location,
                link=link,
                reminder_hours_before=reminder_hours_before,
                active=active,
                updated_at=now,
            )
            db.add(event)

        await db.commit()
        await db.refresh(event)
        return _community_event_to_dict(event)


# ═══════════════════════════════════════════════════════════
# Members
# ═══════════════════════════════════════════════════════════

async def create_member(
    client_id: uuid.UUID,
    name: str,
    whatsapp: str,
    email: Optional[str] = None,
    industry: Optional[str] = None,
    company: Optional[str] = None,
    stage: Optional[str] = None,
    building: Optional[str] = None,
    focus_areas: Optional[List[str]] = None,
    why_community: Optional[str] = None,
    goals: Optional[str] = None,
    revenue_range: Optional[str] = None,
    approved_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a new member record."""
    now = datetime.now(timezone.utc)
    member = Member(
        client_id=client_id,
        name=name,
        whatsapp=whatsapp,
        email=email,
        industry=industry,
        company=company,
        stage=stage,
        building=building,
        focus_areas=focus_areas,
        why_community=why_community,
        goals=goals,
        revenue_range=revenue_range,
        approved_at=approved_at or now,
        approval_source="webhook",
        journey_day=0,
        journey_phase="foundation",
        engagement_score=0.0,
        state="pending",
        created_at=now,
        last_active_at=now,
    )

    async with async_session_maker() as db:
        db.add(member)
        await db.commit()
        await db.refresh(member)

    logger.info(f"Created member {member.id} ({name}) for client {client_id}")
    return _member_to_dict(member)


async def find_member_by_whatsapp(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Find a member by WhatsApp number or LID.
    Tries: LID, @s.whatsapp.net JID, raw number, all Nigerian format variants.
    """
    async with async_session_maker() as db:
        # Normalize: strip +, spaces, dashes
        norm_id = identifier.strip().replace(" ", "").replace("-", "")
        if norm_id.startswith("+"):
            norm_id = norm_id[1:]

        # Build possible identifiers for matching
        possible_ids = [identifier, norm_id]

        # Add Nigerian format variants in BOTH directions
        # Local format: 09167659790 (11 digits, starts with 0)
        if norm_id.startswith("0") and len(norm_id) == 11:
            possible_ids.append("234" + norm_id[1:])       # 2349167659790
            possible_ids.append("+234" + norm_id[1:])      # +2349167659790
        # International format without +: 2349167659790 (13 digits, no +)
        if norm_id.startswith("234") and len(norm_id) == 13:
            possible_ids.append("0" + norm_id[3:])         # 09167659790
            possible_ids.append("+" + norm_id)             # +2349167659790

        stmt = select(Member).where(
            or_(
                Member.whatsapp.in_(possible_ids),
                Member.whatsapp_lid == identifier,
                Member.whatsapp_lid == norm_id,
            )
        ).order_by(Member.created_at.desc()).limit(1)

        result = await db.execute(stmt)
        member = result.scalar_one_or_none()

        if member:
            return _member_to_dict(member)
        return None


async def get_member(member_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get full member profile by ID."""
    async with async_session_maker() as db:
        result = await db.get(Member, member_id)
        if result:
            return _member_to_dict(result)
        return None


async def update_member_state(member_id: uuid.UUID, state: Optional[str] = None, **kwargs):
    """Update member state and optional fields. Skips state if None."""
    async with async_session_maker() as db:
        result = await db.get(Member, member_id)
        if result:
            if state is not None:
                result.state = state
            result.last_active_at = datetime.now(timezone.utc)
            for key, value in kwargs.items():
                if hasattr(result, key):
                    setattr(result, key, value)
            await db.commit()


async def update_member_lid(member_id: uuid.UUID, lid: str):
    """Store or update the WhatsApp LID for a member."""
    async with async_session_maker() as db:
        result = await db.get(Member, member_id)
        if result:
            result.whatsapp_lid = lid
            await db.commit()


async def member_exists(whatsapp: str, client_id: uuid.UUID) -> bool:
    """Check if a member with this whatsapp already exists for this client."""
    async with async_session_maker() as db:
        stmt = select(Member).where(
            and_(
                Member.whatsapp == whatsapp,
                Member.client_id == client_id,
                Member.state.in_(["pending", "active"]),
            )
        ).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None


async def get_active_members(client_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get approved members eligible for proactive community activity."""
    async with async_session_maker() as db:
        stmt = select(Member).where(
            and_(
                Member.client_id == client_id,
                Member.state.in_(["pending", "active"]),
                Member.approved_at != None,
            )
        ).order_by(Member.created_at.asc())
        result = await db.execute(stmt)
        members = result.scalars().all()
        return [_member_to_dict(m) for m in members]


async def get_approved_members(client_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get approved members for manual broadcasts."""
    async with async_session_maker() as db:
        stmt = select(Member).where(
            and_(
                Member.client_id == client_id,
                Member.state.in_(["pending", "active"]),
                Member.approved_at != None,
            )
        ).order_by(Member.created_at.asc())
        result = await db.execute(stmt)
        members = result.scalars().all()
        return [_member_to_dict(m) for m in members]


# ═══════════════════════════════════════════════════════════
# Broadcasts
# ═══════════════════════════════════════════════════════════

async def create_broadcast(
    client_id: uuid.UUID,
    title: str,
    message: str,
    recipients: List[Dict[str, Any]],
    brief: Optional[str] = None,
    include_approved_members: bool = False,
) -> Dict[str, Any]:
    """Create a broadcast draft and its recipient rows."""
    member_count = sum(1 for r in recipients if r.get("source") == "member")
    manual_count = sum(1 for r in recipients if r.get("source") == "manual")
    if include_approved_members and manual_count:
        source = "mixed"
    elif include_approved_members:
        source = "members"
    else:
        source = "manual"

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        broadcast = Broadcast(
            client_id=client_id,
            title=title,
            brief=brief,
            message=message,
            status="draft",
            recipient_source=source,
            include_approved_members=include_approved_members,
            member_count=member_count,
            manual_count=manual_count,
            total_recipients=len(recipients),
            created_at=now,
            updated_at=now,
        )
        db.add(broadcast)
        await db.flush()

        for recipient in recipients:
            db.add(BroadcastRecipient(
                broadcast_id=broadcast.id,
                member_id=recipient.get("member_id"),
                whatsapp=recipient["whatsapp"],
                source=recipient.get("source", "manual"),
                status="pending",
                attempts=0,
                created_at=now,
            ))

        await db.commit()
        await db.refresh(broadcast)
        return _broadcast_to_dict(broadcast)


async def list_broadcasts(client_id: uuid.UUID, limit: int = 50) -> List[Dict[str, Any]]:
    async with async_session_maker() as db:
        stmt = (
            select(Broadcast)
            .where(Broadcast.client_id == client_id)
            .order_by(Broadcast.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        broadcasts = result.scalars().all()
        return [_broadcast_to_dict(b) for b in broadcasts]


async def get_broadcast(broadcast_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    async with async_session_maker() as db:
        broadcast = await db.get(Broadcast, broadcast_id)
        return _broadcast_to_dict(broadcast) if broadcast else None


async def get_broadcast_recipients(
    broadcast_id: uuid.UUID,
    limit: Optional[int] = None,
    statuses: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    async with async_session_maker() as db:
        filters = [BroadcastRecipient.broadcast_id == broadcast_id]
        if statuses:
            filters.append(BroadcastRecipient.status.in_(statuses))
        stmt = select(BroadcastRecipient).where(and_(*filters)).order_by(BroadcastRecipient.created_at.asc())
        if limit:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        recipients = result.scalars().all()
        return [_broadcast_recipient_to_dict(r) for r in recipients]


async def queue_broadcast(broadcast_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    async with async_session_maker() as db:
        broadcast = await db.get(Broadcast, broadcast_id)
        if not broadcast:
            return None
        if broadcast.status not in {"draft", "failed"}:
            return _broadcast_to_dict(broadcast)
        now = datetime.now(timezone.utc)
        broadcast.status = "queued"
        broadcast.queued_at = now
        broadcast.updated_at = now
        await db.commit()
        await db.refresh(broadcast)
        return _broadcast_to_dict(broadcast)


async def get_next_broadcast_to_send() -> Optional[Dict[str, Any]]:
    async with async_session_maker() as db:
        stmt = (
            select(Broadcast)
            .where(Broadcast.status.in_(["queued", "sending"]))
            .order_by(Broadcast.queued_at.asc().nulls_last(), Broadcast.created_at.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        broadcast = result.scalar_one_or_none()
        return _broadcast_to_dict(broadcast) if broadcast else None


async def mark_broadcast_sending(broadcast_id: uuid.UUID):
    async with async_session_maker() as db:
        broadcast = await db.get(Broadcast, broadcast_id)
        if not broadcast:
            return
        now = datetime.now(timezone.utc)
        broadcast.status = "sending"
        if not broadcast.started_at:
            broadcast.started_at = now
        broadcast.updated_at = now
        await db.commit()


async def mark_broadcast_completed_if_done(broadcast_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    async with async_session_maker() as db:
        pending_stmt = select(func.count()).select_from(BroadcastRecipient).where(
            and_(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == "pending",
            )
        )
        pending = (await db.execute(pending_stmt)).scalar() or 0

        broadcast = await db.get(Broadcast, broadcast_id)
        if not broadcast:
            return None

        now = datetime.now(timezone.utc)
        if pending == 0 and broadcast.status in {"queued", "sending"}:
            broadcast.status = "completed"
            broadcast.completed_at = now
        broadcast.updated_at = now
        await db.commit()
        await db.refresh(broadcast)
        return _broadcast_to_dict(broadcast)


async def mark_broadcast_recipient_sent(recipient_id: uuid.UUID):
    async with async_session_maker() as db:
        recipient = await db.get(BroadcastRecipient, recipient_id)
        if not recipient:
            return
        recipient.status = "sent"
        recipient.attempts = (recipient.attempts or 0) + 1
        recipient.last_error = None
        recipient.sent_at = datetime.now(timezone.utc)
        await db.commit()


async def mark_broadcast_recipient_failed(recipient_id: uuid.UUID, error: str, retry_limit: int):
    async with async_session_maker() as db:
        recipient = await db.get(BroadcastRecipient, recipient_id)
        if not recipient:
            return
        recipient.attempts = (recipient.attempts or 0) + 1
        recipient.last_error = error[:500]
        recipient.status = "failed" if recipient.attempts >= retry_limit else "pending"
        await db.commit()


# ═══════════════════════════════════════════════════════════
# Conversations
# ═══════════════════════════════════════════════════════════

async def create_conversation(member_id: uuid.UUID, touchpoint_key: Optional[str] = None) -> Dict[str, Any]:
    """Open a new conversation for a member."""
    conversation = Conversation(
        member_id=member_id,
        touchpoint_key=touchpoint_key,
        opened_at=datetime.now(timezone.utc),
        state="open",
    )

    async with async_session_maker() as db:
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    return _conversation_to_dict(conversation)


async def get_open_conversation(member_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Find the latest open conversation for a member."""
    async with async_session_maker() as db:
        stmt = select(Conversation).where(
            and_(
                Conversation.member_id == member_id,
                Conversation.state == "open",
            )
        ).order_by(Conversation.opened_at.desc()).limit(1)

        result = await db.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv:
            return _conversation_to_dict(conv)
        return None


async def close_conversation(conversation_id: uuid.UUID):
    """Close a conversation."""
    async with async_session_maker() as db:
        result = await db.get(Conversation, conversation_id)
        if result:
            result.state = "closed"
            result.closed_at = datetime.now(timezone.utc)
            await db.commit()


# ═══════════════════════════════════════════════════════════
# Messages
# ═══════════════════════════════════════════════════════════

async def save_message(
    conversation_id: uuid.UUID,
    member_id: uuid.UUID,
    role: str,
    content: str,
    touchpoint_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a message and update member's last_active_at."""
    now = datetime.now(timezone.utc)
    message = Message(
        conversation_id=conversation_id,
        member_id=member_id,
        role=role,
        content=content,
        sent_at=now,
        touchpoint_key=touchpoint_key,
    )

    async with async_session_maker() as db:
        db.add(message)

        # Update member last_active_at
        member = await db.get(Member, member_id)
        if member:
            member.last_active_at = now

        await db.commit()
        await db.refresh(message)

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "member_id": message.member_id,
        "role": message.role,
        "content": message.content,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "touchpoint_key": message.touchpoint_key,
    }


async def get_conversation_messages(conversation_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Load full message history for a conversation, oldest first."""
    async with async_session_maker() as db:
        stmt = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.sent_at.asc())

        result = await db.execute(stmt)
        messages = result.scalars().all()

        return [
            {
                "role": msg.role,
                "content": msg.content,
                "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                "touchpoint_key": msg.touchpoint_key,
            }
            for msg in messages
        ]


async def get_latest_member_message_time(conversation_id: uuid.UUID) -> Optional[datetime]:
    """Get the timestamp of the most recent member message in a conversation."""
    async with async_session_maker() as db:
        stmt = select(func.max(Message.sent_at)).where(
            and_(
                Message.conversation_id == conversation_id,
                Message.role == "member",
            )
        )
        result = await db.execute(stmt)
        return result.scalar()


# ═══════════════════════════════════════════════════════════
# Journey Touchpoints
# ═══════════════════════════════════════════════════════════

async def insert_touchpoint(
    member_id: uuid.UUID,
    touchpoint_key: str,
    scheduled_for: datetime,
    requires_human: bool = False,
) -> Dict[str, Any]:
    """Insert a single touchpoint instance for a member."""
    tp = JourneyTouchpoint(
        member_id=member_id,
        touchpoint_key=touchpoint_key,
        scheduled_for=scheduled_for,
        state="pending",
        requires_human=requires_human,
        nudge_sent=False,
    )

    async with async_session_maker() as db:
        db.add(tp)
        await db.commit()
        await db.refresh(tp)

    return _touchpoint_to_dict(tp)


async def touchpoint_exists_between(
    member_id: uuid.UUID,
    touchpoint_key: str,
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    """Check whether a member already has this touchpoint in a time window."""
    async with async_session_maker() as db:
        stmt = select(JourneyTouchpoint.id).where(
            and_(
                JourneyTouchpoint.member_id == member_id,
                JourneyTouchpoint.touchpoint_key == touchpoint_key,
                JourneyTouchpoint.scheduled_for >= starts_at,
                JourneyTouchpoint.scheduled_for < ends_at,
            )
        ).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None


async def get_pending_touchpoints() -> List[Dict[str, Any]]:
    """
    Find all touchpoints that are pending and past their scheduled time.
    Excludes requires_human touchpoints (handled via dashboard).
    """
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        stmt = select(JourneyTouchpoint).where(
            and_(
                JourneyTouchpoint.state == "pending",
                JourneyTouchpoint.scheduled_for <= now,
                JourneyTouchpoint.requires_human == False,
            )
        ).order_by(JourneyTouchpoint.scheduled_for.asc())

        result = await db.execute(stmt)
        touchpoints = result.scalars().all()

        return [_touchpoint_to_dict(t) for t in touchpoints]


async def get_pending_human_touchpoints() -> List[Dict[str, Any]]:
    """Find due touchpoints that require a human admin action."""
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        stmt = select(JourneyTouchpoint).where(
            and_(
                JourneyTouchpoint.state == "pending",
                JourneyTouchpoint.scheduled_for <= now,
                JourneyTouchpoint.requires_human == True,
            )
        ).order_by(JourneyTouchpoint.scheduled_for.asc())

        result = await db.execute(stmt)
        touchpoints = result.scalars().all()

        return [_touchpoint_to_dict(t) for t in touchpoints]


async def get_touchpoints_needing_nudge(delay_mins: int) -> List[Dict[str, Any]]:
    """
    Find touchpoints in 'in_conversation' state where the last member message
    was more than `delay_mins` ago and no nudge has been sent yet.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=delay_mins)

    async with async_session_maker() as db:
        # Subquery: get last member message time per conversation
        last_msg = (
            select(
                Message.conversation_id,
                func.max(Message.sent_at).label("last_reply_at"),
            )
            .where(Message.role == "member")
            .group_by(Message.conversation_id)
            .subquery()
        )

        stmt = (
            select(JourneyTouchpoint)
            .join(
                last_msg,
                JourneyTouchpoint.conversation_id == last_msg.c.conversation_id,
                isouter=True,
            )
            .where(
                and_(
                    JourneyTouchpoint.state == "in_conversation",
                    JourneyTouchpoint.requires_human == False,
                    JourneyTouchpoint.nudge_sent == False,
                    or_(
                        last_msg.c.last_reply_at == None,
                        last_msg.c.last_reply_at < cutoff,
                    ),
                )
            )
        )

        result = await db.execute(stmt)
        touchpoints = result.scalars().all()

        return [_touchpoint_to_dict(t) for t in touchpoints]


async def get_timed_out_touchpoints(hours: int) -> List[Dict[str, Any]]:
    """
    Find touchpoints in 'in_conversation' state with no member reply
    in the last `hours` hours. Mark them for timeout.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session_maker() as db:
        last_msg = (
            select(
                Message.conversation_id,
                func.max(Message.sent_at).label("last_reply_at"),
            )
            .where(Message.role == "member")
            .group_by(Message.conversation_id)
            .subquery()
        )

        stmt = (
            select(JourneyTouchpoint)
            .join(
                last_msg,
                JourneyTouchpoint.conversation_id == last_msg.c.conversation_id,
                isouter=True,
            )
            .where(
                and_(
                    JourneyTouchpoint.state == "in_conversation",
                    or_(
                        last_msg.c.last_reply_at == None,
                        last_msg.c.last_reply_at < cutoff,
                    ),
                )
            )
        )

        result = await db.execute(stmt)
        touchpoints = result.scalars().all()

        return [_touchpoint_to_dict(t) for t in touchpoints]


async def get_disengaged_members(threshold: float, min_days: int, client_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Find members with engagement_score < threshold who have been active
    for at least min_days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_days)

    async with async_session_maker() as db:
        stmt = select(Member).where(
            and_(
                Member.client_id == client_id,
                Member.engagement_score < threshold,
                Member.created_at <= cutoff,
                Member.state == "active",
            )
        )
        result = await db.execute(stmt)
        members = result.scalars().all()

        return [_member_to_dict(m) for m in members]


async def get_touchpoints_by_member(member_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Get all touchpoints for a member, ordered by scheduled_for."""
    async with async_session_maker() as db:
        stmt = select(JourneyTouchpoint).where(
            JourneyTouchpoint.member_id == member_id
        ).order_by(JourneyTouchpoint.scheduled_for.asc())

        result = await db.execute(stmt)
        touchpoints = result.scalars().all()

        return [_touchpoint_to_dict(t) for t in touchpoints]


async def get_touchpoint(touchpoint_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get a single touchpoint by ID."""
    async with async_session_maker() as db:
        result = await db.get(JourneyTouchpoint, touchpoint_id)
        if result:
            return _touchpoint_to_dict(result)
        return None


async def get_touchpoint_with_member(touchpoint_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get a touchpoint with its member data joined."""
    async with async_session_maker() as db:
        stmt = (
            select(JourneyTouchpoint, Member)
            .join(Member, JourneyTouchpoint.member_id == Member.id)
            .where(JourneyTouchpoint.id == touchpoint_id)
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        if row:
            tp, member = row
            data = _touchpoint_to_dict(tp)
            data["member"] = _member_to_dict(member)
            return data
        return None


async def get_touchpoint_by_conversation(conversation_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Find a touchpoint linked to a conversation."""
    async with async_session_maker() as db:
        stmt = select(JourneyTouchpoint).where(
            JourneyTouchpoint.conversation_id == conversation_id
        ).limit(1)
        result = await db.execute(stmt)
        tp = result.scalar_one_or_none()
        if tp:
            return _touchpoint_to_dict(tp)
        return None


async def update_touchpoint(touchpoint_id: uuid.UUID, **kwargs):
    """Update touchpoint fields."""
    async with async_session_maker() as db:
        result = await db.get(JourneyTouchpoint, touchpoint_id)
        if result:
            for key, value in kwargs.items():
                if hasattr(result, key):
                    setattr(result, key, value)
            await db.commit()


async def set_touchpoint_fired(touchpoint_id: uuid.UUID, conversation_id: uuid.UUID):
    """Mark a touchpoint as fired and link its conversation."""
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        result = await db.get(JourneyTouchpoint, touchpoint_id)
        if result:
            result.state = "in_conversation"
            result.fired_at = now
            result.conversation_id = conversation_id
            await db.commit()


async def complete_touchpoint(touchpoint_id: uuid.UUID):
    """Mark a touchpoint as completed."""
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        result = await db.get(JourneyTouchpoint, touchpoint_id)
        if result:
            result.state = "completed"
            result.completed_at = now
            await db.commit()


async def mark_touchpoint_nudged(touchpoint_id: uuid.UUID):
    """Mark that a nudge has been sent for this touchpoint."""
    async with async_session_maker() as db:
        result = await db.get(JourneyTouchpoint, touchpoint_id)
        if result:
            result.nudge_sent = True
            await db.commit()
