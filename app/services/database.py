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
    Create or update the default client from env settings.
    Returns the client dict.
    """
    async with async_session_maker() as db:
        stmt = select(Client).limit(1)
        result = await db.execute(stmt)
        client = result.scalar_one_or_none()

        if client:
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
            )
            db.add(client)

        await db.commit()
        await db.refresh(client)
        logger.info(f"Default client synced: {client.id} ({client.community_name})")
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
