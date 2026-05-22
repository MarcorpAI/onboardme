"""
OnboardMe V2 — Journey Engine
Defines the 90-day touchpoint schedule and handles scheduling + firing logic.
"""

from datetime import datetime, timedelta, timezone
import asyncio
from typing import List, Dict, Any, Optional
import uuid
import logging

from app.config import settings
from app.services.database import (
    insert_touchpoint,
    set_touchpoint_fired,
    complete_touchpoint,
    mark_touchpoint_nudged,
    update_member_state,
    create_conversation,
    save_message,
    get_member,
    get_template,
    get_templates_for_client,
    get_touchpoint_with_member,
    get_touchpoints_by_member,
    get_conversation_messages,
    close_conversation,
    update_touchpoint,
    get_open_conversation,
    get_groups_for_client,
    get_upcoming_events_for_client,
    get_events_due_for_reminders,
    get_event,
    get_active_members,
    touchpoint_exists_between,
)
from app.services.groq import groq_service
from app.services.whatsapp import whatsapp_service

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Touchpoint Schedule Definition
# ═══════════════════════════════════════════════════════════

# Each entry defines a touchpoint template that gets seeded for every client.
# When a member is approved, an instance of every automated touchpoint
# is created with an absolute timestamp.

TouchpointDef = Dict[str, Any]

TOUCHPOINT_SCHEDULE: List[TouchpointDef] = [
    {
        "day": 1,
        "key": "day_1_community_orientation",
        "name": "Community Orientation",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Welcome the approved member and progressively introduce the MBN ecosystem.",
        "cta": "Start a conversation that helps the member understand MBN step by step, join the right groups, and share their own first goal or intro.",
        "brief": "This is the first conversation after approval. Keep the reply specific to MBN, not general community advice. Do not explain every MBN group in one message. Start with a warm welcome and a high-level explanation of MBN as a builder-focused ecosystem. Ask one short question or give one small CTA. As the member replies, continue progressively through Active Builders, Members Visibility, Café, Opportunities, Marketplace, and All Access Learning Lab. Route them toward posting inside the relevant community groups, not only chatting privately with the AI. Do not offer to do, create, or handle an intro for the member. If an intro is relevant, ask them to share it themselves and optionally suggest the simple format: who they are, what they are building, and what they want support with.",
        "fallback_message": "Welcome again. When you get a moment, I can walk you through how to get the best out of MBN step by step.",
    },
    {
        "day": 1,
        "key": "weekly_build_in_public",
        "name": "Build in Public Monday",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Prompt the member to share weekly goals, progress, blockers, and plans in Active Builders.",
        "cta": "Get the member to post their Build in Public update in Active Builders.",
        "brief": "Monday MBN activity. Encourage the member to share what they are working on, their weekly goals, current progress, blockers, and plans in Active Builders. If they tell you privately, acknowledge it and still route them to share the useful version in the group.",
        "fallback_message": "Quick Monday nudge: share your Build in Public update in Active Builders so the community can track and support your progress.",
    },
    {
        "day": 1,
        "key": "weekly_member_visibility",
        "name": "Member Visibility Thursday",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Prompt the member to promote their business, product, service, or profile in Members Visibility.",
        "cta": "Get the member to post a visibility update in Members Visibility.",
        "brief": "Thursday MBN activity. Help the member become visible by sharing a business post, social profile, product/service offer, portfolio, promotion, or announcement in Members Visibility. Keep it practical and confidence-building.",
        "fallback_message": "Today is Member Visibility Thursday. Share one offer, link, or business update in Members Visibility so more people know what you do.",
    },
    {
        "day": 1,
        "key": "weekly_little_wins",
        "name": "Little Wins Friday",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Prompt the member to reflect on and share a weekly win in Active Builders.",
        "cta": "Get the member to post one small or big win in Active Builders.",
        "brief": "Friday MBN activity. Encourage reflection and celebration of progress: sales, completed tasks, skills learned, problems solved, goal progress, or new opportunities. If they say the win privately, encourage them to share it in Active Builders.",
        "fallback_message": "Little Wins Friday is for progress, even small progress. Share one win from this week in Active Builders.",
    },
    {
        "day": 1,
        "key": "checkin_midweek_progress",
        "name": "Midweek Progress Check-in",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Check how the member is progressing on what they said they were working on.",
        "cta": "Get a progress update and route useful updates or blockers to the right MBN group.",
        "brief": "Light accountability check-in. Ask how far they have gone with the thing they said they were working on. If there is a blocker, suggest sharing it in Active Builders or the most relevant group. Do not sound like a daily reminder bot.",
        "fallback_message": "Midweek check-in: how far have you gone with what you planned to work on this week?",
    },
    {
        "day": 1,
        "key": "checkin_weekend_reflection",
        "name": "Weekend Reflection Check-in",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "community",
        "purpose": "Prompt a light reflection after the weekly activity cycle.",
        "cta": "Help the member identify what moved forward and what should be shared in the community.",
        "brief": "Light weekend-adjacent check-in. Ask what moved forward this week or what they need support with before the next week. Route wins to Active Builders, offers to Marketplace or Members Visibility, and opportunities/resources to the right groups.",
        "fallback_message": "Quick reflection: what moved forward for you this week, and what do you need support with next?",
    },
    # ── Foundation Phase (Days 1–14) ──
    {
        "day": 1,
        "key": "day_1_welcome",
        "name": "Welcome DM",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Welcome the member warmly, introduce the community, and set the tone for the journey.",
        "cta": "Get the member to reply and start a conversation. After they reply, naturally guide them with orientation — what to do first in the community.",
        "brief": "This is Day 1 — the member was just approved. Send a short, warm welcome. Ask what they're working on. Do NOT pitch anything. Do NOT send the invite link yet. Once they reply, you can naturally share a couple of first steps: introduce themselves, check out ongoing conversations, set up their profile. The orientation should feel like a natural conversation, not a checklist.",
        "fallback_message": "Hey! Just wanted to say welcome again. When you get a moment, I'd love to hear what you're working on.",
    },
    {
        "day": 2,
        "key": "day_2_buddy_intro",
        "name": "Buddy Intro",
        "automation": False,
        "conditional": False,
        "requires_human": True,
        "phase": "foundation",
        "purpose": "Introduce the member to their onboarding buddy via a 3-way WhatsApp group.",
        "cta": "Admin matches buddy and creates group.",
        "brief": "This touchpoint requires a human admin to create a 3-way WhatsApp group introducing the member to their onboarding buddy. Surfaced in the dashboard for manual action.",
    },
    {
        "day": 3,
        "key": "day_3_no_response",
        "name": "No Response Follow-up",
        "automation": True,
        "conditional": True,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Re-engage the member if they haven't replied to Day 1 messages.",
        "cta": "Get the member to reply and start the conversation.",
        "brief": "The member hasn't replied to the Day 1 welcome. Send a very short, warm check-in. No pressure, no repeat of the original question. Just a gentle nudge to see if they're still interested.",
        "fallback_message": "Just checking in — no rush at all. I'm here whenever you're ready to chat.",
    },
    {
        "day": 5,
        "key": "day_5_checkin",
        "name": "First Personal Check-in",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Check in personally with the member and build rapport.",
        "cta": "Get the member to share something about their week or current focus.",
        "brief": "Day 5 — a personal check-in. Ask how their week is going. Show genuine interest in what they're working on. This builds the relationship.",
        "fallback_message": "Hey, hope your week is going well! Just wanted to check in and see how things are going on your end.",
    },
    {
        "day": 7,
        "key": "day_7_focus",
        "name": "Focus Question",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Understand what the member is most focused on in their business right now.",
        "cta": "Get a clear answer to 'what's the one thing you're most focused on right now?' and acknowledge it warmly.",
        "brief": "Day 7 — the member has been in the community for a week. Ask what's taking most of their energy in their business right now. This answer helps connect them to the right people and conversations. Do not pitch anything. Just have a genuine conversation.",
        "fallback_message": "Hey! One question before the weekend — what's the one thing you're most focused on in your business right now?",
    },
    {
        "day": 9,
        "key": "day_9_operator_session",
        "name": "Operator Session Invite",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Invite the member to the next Operator Session (group coaching/Q&A).",
        "cta": "Get the member to confirm interest and book or save the date.",
        "brief": "Day 9 — invite the member to the upcoming Operator Session. Share the link if available. Keep it casual — 'we have this session coming up, thought you might find it useful.'",
        "fallback_message": "Quick heads up — our next Operator Session is coming up. It's a live Q&A for members. Let me know if you'd like the details!",
    },
    {
        "day": 14,
        "key": "day_14_two_week_checkin",
        "name": "2-Week Check-in",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "foundation",
        "purpose": "Reflect on the first two weeks and reinforce value.",
        "cta": "Get the member to share what they've found most valuable so far, and address any early concerns.",
        "brief": "Two weeks in! Ask the member how it's been so far — what they've enjoyed, what they've found valuable, and if anything's been confusing. This is also a good moment to share the invite link if they're ready.",
        "fallback_message": "Two weeks in — how are you finding the community so far? Anything you've especially enjoyed or found helpful?",
    },

    # ── Integration Phase (Days 15–56) ──
    {
        "day": 15,
        "key": "day_15_session_reminder",
        "name": "Session Reminder (48hrs)",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Remind the member about an upcoming session they were invited to.",
        "cta": "Confirm attendance or get the member to book.",
        "brief": "Day 15 — the Operator Session or similar event is 48 hours away. Send a friendly reminder. Include the link again. Keep it short.",
        "fallback_message": "Just a reminder — the session is coming up in 2 days! Details here if you need them.",
    },
    {
        "day": 21,
        "key": "day_21_yellow_flag",
        "name": "Yellow Flag DM",
        "automation": True,
        "conditional": True,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Re-engage a member who has gone silent (engagement_score < threshold).",
        "cta": "Get the member to reply and re-engage.",
        "brief": "This is a re-engagement message for a member who has been quiet. Be warm, not accusatory. 'Haven't heard from you in a bit — just checking if everything's okay.' No pitch. No CTA beyond a reply.",
        "fallback_message": "Hey! Haven't heard from you in a bit. Hope everything's going well — just checking in.",
    },
    {
        "day": 21,
        "key": "day_21_red_flag",
        "name": "Red Flag Escalation",
        "automation": False,
        "conditional": True,
        "requires_human": True,
        "phase": "integration",
        "purpose": "Escalate a deeply disengaged member to a human for a personal call.",
        "cta": "Admin calls the member personally.",
        "brief": "This member has been silent for an extended period and hasn't responded to the Yellow Flag. A human admin needs to make a personal call. Surfaced in the dashboard.",
    },
    {
        "day": 28,
        "key": "day_28_four_week_checkin",
        "name": "4-Week Check-in",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Check in at the one-month mark and reinforce value.",
        "cta": "Get the member to reflect on their first month and share any wins or challenges.",
        "brief": "One month in! Ask the member how things are going. Any wins? Any challenges? This is a good moment to remind them of key resources or upcoming events.",
        "fallback_message": "A month in — how are things going? Any wins you've had or challenges you're working through?",
    },
    {
        "day": 30,
        "key": "day_30_wellbeing",
        "name": "Personal Wellbeing Check",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Check in on the member's personal wellbeing and mental health.",
        "cta": "Create a safe space for the member to share how they're really doing.",
        "brief": "Day 30 — a personal wellbeing check. Ask how they're doing — not just in business, but personally. Founders carry a lot. Make it clear this is a safe space. Do not push any CTA or agenda.",
        "fallback_message": "Hey — just checking in on you. How are you really doing?",
    },
    {
        "day": 35,
        "key": "day_35_founder_lab_pitch",
        "name": "Founder Lab Pitch",
        "automation": False,
        "conditional": True,
        "requires_human": True,
        "phase": "integration",
        "purpose": "Invite high-potential members to join the Founder Lab programme.",
        "cta": "Admin reviews member profile and sends personalised invitation if appropriate.",
        "brief": "This is a manual touchpoint for the admin. If the member's profile (stage, building, goals) matches Founder Lab criteria, send a personalised invitation. Surfaced in the dashboard.",
    },
    {
        "day": 35,
        "key": "day_35_founder_stories",
        "name": "Founder Stories Invite",
        "automation": True,
        "conditional": True,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Invite the member to share their founder story for the community newsletter/socials.",
        "cta": "Get the member to express interest in being featured.",
        "brief": "Day 35 — invite the member to share their story for Founder Stories. Keep it optional and low-pressure. 'Would you be open to sharing your journey so far?'",
        "fallback_message": "We'd love to feature your founder journey in our stories series. No pressure — but if you're open to it, let me know!",
    },
    {
        "day": 42,
        "key": "day_42_session_feedback",
        "name": "Operator Session Feedback",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Collect feedback from the member on sessions they've attended.",
        "cta": "Get the member to share what they thought of recent sessions and what they'd like more of.",
        "brief": "Day 42 — ask the member for feedback on the sessions they've attended. What was useful? What could be better? This shows their opinion matters.",
        "fallback_message": "Quick question — what have you thought of the sessions so far? Any feedback on what you'd like more of?",
    },
    {
        "day": 49,
        "key": "day_49_spotlight",
        "name": "Member Spotlight Invite",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Invite the member to be featured in the member spotlight series.",
        "cta": "Get the member to agree to be featured and share their story.",
        "brief": "Day 49 — the member has been around for 7 weeks. Invite them to be featured in the Member Spotlight. It's a chance to share their journey with the community.",
        "fallback_message": "Would you be open to being featured in our Member Spotlight? We'd love to share your journey with the community.",
    },
    {
        "day": 56,
        "key": "day_56_buddy_closure",
        "name": "Buddy Closure",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "integration",
        "purpose": "Close out the formal buddy relationship and reflect on the experience.",
        "cta": "Get the member to reflect on the buddy experience and transition to full community member.",
        "brief": "Day 56 — the formal buddy programme ends this week. Ask the member how the experience was and let them know they're now a full community member.",
        "fallback_message": "The buddy programme wraps up this week — how was the experience for you? You're now a full member of the community!",
    },

    # ── Consolidation Phase (Days 57–90) ──
    {
        "day": 60,
        "key": "day_60_review_invite",
        "name": "60-Day Review Invite",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "consolidation",
        "purpose": "Invite the member to a 60-day review call (Calendly) to assess progress.",
        "cta": "Get the member to book a 60-day review call.",
        "brief": "Day 60 — invite the member to book a 60-day review call. Share the Calendly link. The call is a chance to reflect on their journey so far and set goals for the next phase.",
        "fallback_message": "Would you be up for a 60-day review call? It's a chance to reflect on your journey and plan next steps. Here's my calendar link.",
    },
    {
        "day": 90,
        "key": "day_90_integration_confirmed",
        "name": "Integration Confirmed",
        "automation": True,
        "conditional": False,
        "requires_human": False,
        "phase": "consolidation",
        "purpose": "Celebrate the member completing the 90-day journey and confirm full integration.",
        "cta": "Celebrate the milestone and welcome the member as a fully integrated community member.",
        "brief": "Day 90 — the full journey is complete! Celebrate with the member. Thank them for the journey, acknowledge their growth, and welcome them as a fully integrated member. This is the last automated touchpoint.",
        "fallback_message": "Congratulations! You've completed the 90-day onboarding journey. Welcome as a fully integrated member of the community. We're glad you're here.",
    },
]

# Index touchpoints by key for quick lookup
TOUCHPOINT_MAP: Dict[str, TouchpointDef] = {tp["key"]: tp for tp in TOUCHPOINT_SCHEDULE}

DAY1_ORIENTATION_KEY = "day_1_community_orientation"
COMMUNITY_RECURRING_KEYS = {
    "weekly_build_in_public",
    "weekly_member_visibility",
    "weekly_little_wins",
    "checkin_midweek_progress",
    "checkin_weekend_reflection",
}
COMMUNITY_TOUCHPOINT_KEYS = {DAY1_ORIENTATION_KEY, *COMMUNITY_RECURRING_KEYS}
SEND_AND_COMPLETE_KEYS = COMMUNITY_RECURRING_KEYS
EVENT_REMINDER_PREFIX = "event_reminder_"
WAT = timezone(timedelta(hours=1))

PROGRESS_GATE_EXEMPT_KEYS = {
    "day_1_orientation_checklist",
    "day_3_no_response",
}

PROGRESS_BLOCKING_TOUCHPOINT_KEYS = {
    "day_1_welcome",
    "day_1_orientation_checklist",
    "day_3_no_response",
    "day_60_review_call",
}

UNRESOLVED_STATES = {"pending", "in_conversation", "needs_human"}


def get_scheduled_touchpoints() -> List[TouchpointDef]:
    """Return all touchpoints that are eligible for automated scheduling."""
    return [tp for tp in TOUCHPOINT_SCHEDULE if (tp["automation"] or tp["requires_human"]) and tp["key"] in COMMUNITY_TOUCHPOINT_KEYS]


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def can_fire_touchpoint(touchpoint: Dict[str, Any]) -> tuple[bool, str]:
    """
    Treat scheduled_for as the earliest eligible time.
    Normal touchpoints wait while the member has an unresolved active/earlier step.
    """
    touchpoint_key = touchpoint["touchpoint_key"]
    if touchpoint.get("requires_human"):
        return True, "human action"

    if touchpoint_key.startswith(EVENT_REMINDER_PREFIX):
        return True, "event reminder"

    if touchpoint_key in COMMUNITY_RECURRING_KEYS:
        return True, "community activity"

    if touchpoint_key in PROGRESS_GATE_EXEMPT_KEYS:
        return True, "exempt"

    scheduled_for = _parse_iso_datetime(touchpoint.get("scheduled_for"))
    member_touchpoints = await get_touchpoints_by_member(touchpoint["member_id"])

    for other in member_touchpoints:
        if other["id"] == touchpoint["id"]:
            continue

        other_state = other.get("state")
        other_key = other.get("touchpoint_key")
        other_scheduled_for = _parse_iso_datetime(other.get("scheduled_for"))

        if other_state == "in_conversation":
            return False, f"active touchpoint {other_key} is still in conversation"

        if (
            scheduled_for
            and other_scheduled_for
            and other_scheduled_for < scheduled_for
            and other_state in UNRESOLVED_STATES
            and other_key in PROGRESS_BLOCKING_TOUCHPOINT_KEYS
        ):
            return False, f"earlier blocking touchpoint {other_key} is unresolved"

    return True, "eligible"


# ═══════════════════════════════════════════════════════════
# Scheduling
# ═══════════════════════════════════════════════════════════

async def schedule_journey(member_id: uuid.UUID, approved_at: datetime, client_id: uuid.UUID) -> int:
    """
    Calculate and insert all touchpoint instances for a member's 90-day journey.
    Returns the number of touchpoints scheduled.
    """
    count = 0
    templates = [
        template
        for template in await get_templates_for_client(client_id)
        if template.get("touchpoint_key") == DAY1_ORIENTATION_KEY
    ]
    schedule_items = templates or [TOUCHPOINT_MAP[DAY1_ORIENTATION_KEY]]

    for tp_def in schedule_items:
        # Day 1 = 0 days offset (fires immediately)
        # Day 2 = 1 day offset (24h after approval)
        # Day N = N-1 days offset
        scheduled_for = _calculate_scheduled_for(
            approved_at=approved_at,
            day=tp_def.get("day") or 1,
            send_time=tp_def.get("send_time"),
        )

        await insert_touchpoint(
            member_id=member_id,
            touchpoint_key=tp_def.get("touchpoint_key") or tp_def["key"],
            scheduled_for=scheduled_for,
            requires_human=tp_def.get("requires_human", False),
        )
        count += 1

    # Update member state to active
    await update_member_state(
        member_id,
        state="active",
        journey_phase="foundation",
        journey_day=0,
    )

    logger.info(f"Scheduled {count} touchpoints for member {member_id}")
    return count


def _calculate_scheduled_for(approved_at: datetime, day: int, send_time: Optional[str] = None) -> datetime:
    """Calculate the absolute fire time for a journey touchpoint."""
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=timezone.utc)

    scheduled_for = approved_at + timedelta(days=day - 1)
    if not send_time:
        return scheduled_for

    hour, minute = [int(part) for part in send_time.split(":", 1)]
    scheduled_for = scheduled_for.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day == 1 and scheduled_for < approved_at:
        return approved_at
    return scheduled_for


async def run_automation_loop():
    """Small in-process scheduler for touchpoint lifecycle work."""
    logger.info("Starting automation loop")
    while True:
        try:
            from app.routes.jobs import (
                fire_pending_touchpoints,
                nudge_silent_conversations,
                timeout_stale_touchpoints,
                schedule_community_rhythm,
                schedule_event_reminders,
            )

            await timeout_stale_touchpoints()
            await nudge_silent_conversations()
            await schedule_community_rhythm()
            await schedule_event_reminders()
            await fire_pending_touchpoints()
        except Exception as e:
            logger.exception(f"Automation loop error: {e}")

        await asyncio.sleep(300)


def _wat_window_for(date_time: datetime) -> tuple[datetime, datetime]:
    local = date_time.astimezone(WAT)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _scheduled_today_utc(now: datetime, hour: int = 9, minute: int = 0) -> datetime:
    local = now.astimezone(WAT)
    scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return scheduled.astimezone(timezone.utc)


def due_community_touchpoints(now: Optional[datetime] = None) -> List[tuple[str, datetime]]:
    """Return recurring community touchpoints due today at/after 9 AM WAT."""
    now = now or datetime.now(timezone.utc)
    scheduled_for = _scheduled_today_utc(now)
    if now < scheduled_for:
        return []

    weekday = now.astimezone(WAT).weekday()
    mapping = {
        0: ["weekly_build_in_public"],
        2: ["checkin_midweek_progress"],
        3: ["weekly_member_visibility"],
        4: ["weekly_little_wins"],
        5: ["checkin_weekend_reflection"],
    }
    return [(key, scheduled_for) for key in mapping.get(weekday, [])]


async def schedule_due_community_touchpoints(client_id: uuid.UUID, now: Optional[datetime] = None) -> Dict[str, int]:
    """Create missing recurring community touchpoints for all approved active members."""
    now = now or datetime.now(timezone.utc)
    due_items = due_community_touchpoints(now)
    if not due_items:
        return {"members": 0, "created": 0}

    members = await get_active_members(client_id)
    created = 0
    for member in members:
        for touchpoint_key, scheduled_for in due_items:
            window_start, window_end = _wat_window_for(scheduled_for)
            exists = await touchpoint_exists_between(member["id"], touchpoint_key, window_start, window_end)
            if exists:
                continue
            await insert_touchpoint(
                member_id=member["id"],
                touchpoint_key=touchpoint_key,
                scheduled_for=scheduled_for,
                requires_human=False,
            )
            created += 1

    return {"members": len(members), "created": created}


def is_community_touchpoint_key(touchpoint_key: str) -> bool:
    return touchpoint_key in COMMUNITY_TOUCHPOINT_KEYS or touchpoint_key.startswith(EVENT_REMINDER_PREFIX)


def event_reminder_key(event_id: uuid.UUID | str) -> str:
    return f"{EVENT_REMINDER_PREFIX}{event_id}"


async def schedule_due_event_reminders(client_id: uuid.UUID, now: Optional[datetime] = None) -> Dict[str, int]:
    """Create missing event reminder touchpoints for all approved active members."""
    now = now or datetime.now(timezone.utc)
    events = await get_events_due_for_reminders(client_id, now)
    if not events:
        return {"members": 0, "events": 0, "created": 0}

    members = await get_active_members(client_id)
    created = 0
    for event in events:
        starts_at = _parse_iso_datetime(event["starts_at"])
        if not starts_at:
            continue
        touchpoint_key = event_reminder_key(event["id"])
        scheduled_for = now
        window_start = starts_at - timedelta(hours=max(event.get("reminder_hours_before") or 24, 1))
        window_end = starts_at
        for member in members:
            exists = await touchpoint_exists_between(member["id"], touchpoint_key, window_start, window_end)
            if exists:
                continue
            await insert_touchpoint(
                member_id=member["id"],
                touchpoint_key=touchpoint_key,
                scheduled_for=scheduled_for,
                requires_human=False,
            )
            created += 1

    return {"members": len(members), "events": len(events), "created": created}


def _build_event_template(event: Dict[str, Any]) -> Dict[str, Any]:
    title = event.get("title") or "Upcoming MBN event"
    starts_at = event.get("starts_at") or "the scheduled time"
    description = event.get("description") or "An upcoming MBN community event."
    location = event.get("location") or "the event location/details shared by MBN"
    link = event.get("link")
    link_note = f" Share this link only when making the CTA: {link}" if link else " If no link is available, do not invent one."
    return {
        "touchpoint_key": event_reminder_key(event["id"]),
        "name": f"Event Reminder: {title}",
        "purpose": f"Remind the member about the upcoming MBN event: {title}.",
        "cta": "Get the member to note the event and attend or register if the link is available.",
        "brief": (
            f"This is an event reminder, not a weekly community rhythm message. Event: {title}. "
            f"Date/time: {starts_at}. Description: {description}. Location: {location}."
            f"{link_note} Keep it short and useful. Do not say the member is registered unless the conversation history proves it."
        ),
        "active": bool(event.get("active", True)),
    }


# ═══════════════════════════════════════════════════════════
# Firing Touchpoints
# ═══════════════════════════════════════════════════════════

async def fire_touchpoint(touchpoint_id: uuid.UUID) -> bool:
    """
    Fire a single touchpoint:
    1. Create a conversation for this touchpoint
    2. Get the template + member data
    3. Call AI to generate the opening message
    4. Send via WhatsApp
    5. Save the message and update state

    Returns True if successful, False otherwise.
    """
    try:
        # 1. Get touchpoint with member data
        tp_data = await get_touchpoint_with_member(touchpoint_id)
        if not tp_data:
            logger.error(f"Touchpoint {touchpoint_id} not found")
            return False

        member = tp_data["member"]
        touchpoint_key = tp_data["touchpoint_key"]
        tp_def = TOUCHPOINT_MAP.get(touchpoint_key)

        # 2. Skip if conditional and conditions aren't met
        if tp_def and tp_def.get("conditional"):
            should_fire = await _check_conditional(tp_data, tp_def)
            if not should_fire:
                logger.info(f"Skipping conditional touchpoint {touchpoint_key} for member {member['id']}")
                await complete_touchpoint(touchpoint_id)
                return False

        # 3. Get the client context for AI
        from app.services.database import get_default_client
        client_data = await get_default_client()
        if not client_data:
            logger.error("No default client found")
            return False

        # 4. Get template
        template = await get_template(client_data["id"], touchpoint_key)
        if not template and touchpoint_key.startswith(EVENT_REMINDER_PREFIX):
            event_id = touchpoint_key.removeprefix(EVENT_REMINDER_PREFIX)
            try:
                event = await get_event(uuid.UUID(event_id))
            except ValueError:
                event = None
            if event and event["client_id"] == client_data["id"]:
                template = _build_event_template(event)
        if not template or not template.get("active", True):
            logger.info(f"Skipping touchpoint {touchpoint_key}: template or event missing/inactive")
            await complete_touchpoint(touchpoint_id)
            return False
        if template:
            template["community_groups"] = await get_groups_for_client(client_data["id"])
            template["community_events"] = await get_upcoming_events_for_client(client_data["id"])

        # 5. Use the current open conversation when possible so community
        # activities can be woven into an active chat instead of skipped.
        conv = await get_open_conversation(member["id"])
        if not conv:
            conv = await create_conversation(member["id"], touchpoint_key)
        conversation_id = conv["id"]
        history = await get_conversation_messages(conversation_id) if conv else []

        # 6. Call AI to generate opening message
        response_text = groq_service.generate_response(
            client_data=client_data,
            member=member,
            messages=history,
            template=template,
        )

        # 7. Send via WhatsApp
        recipient = member.get("whatsapp_lid") or member.get("whatsapp")
        sent, jid = await whatsapp_service.send_message(recipient, response_text)

        if not sent:
            logger.error(f"Failed to send message for touchpoint {touchpoint_key} to {recipient}")
            # Still save the message but mark as failed send
            await save_message(
                conversation_id=conversation_id,
                member_id=member["id"],
                role="agent",
                content=response_text,
                touchpoint_key=touchpoint_key,
            )
            return False

        # 8. Save agent message
        await save_message(
            conversation_id=conversation_id,
            member_id=member["id"],
            role="agent",
            content=response_text,
            touchpoint_key=touchpoint_key,
        )

        # 9. Recurring community prompts are send-and-complete so they do not
        # block the next activity. The open conversation still carries context.
        if touchpoint_key in SEND_AND_COMPLETE_KEYS or touchpoint_key.startswith(EVENT_REMINDER_PREFIX):
            await set_touchpoint_fired(touchpoint_id, conversation_id)
            await complete_touchpoint(touchpoint_id)
        else:
            await set_touchpoint_fired(touchpoint_id, conversation_id)

        if touchpoint_key == "day_1_orientation_checklist":
            for prior in await get_touchpoints_by_member(member["id"]):
                if prior["touchpoint_key"] == "day_1_welcome" and prior["state"] in UNRESOLVED_STATES:
                    if prior.get("conversation_id"):
                        await close_conversation(prior["conversation_id"])
                    await complete_touchpoint(prior["id"])

        if touchpoint_key == "day_3_no_response":
            for prior in await get_touchpoints_by_member(member["id"]):
                if prior["touchpoint_key"] in {"day_1_welcome", "day_1_orientation_checklist"} and prior["state"] in UNRESOLVED_STATES:
                    if prior.get("conversation_id"):
                        await close_conversation(prior["conversation_id"])
                    await complete_touchpoint(prior["id"])

        # 10. Store JID if bridge returned new one and we don't have it
        if jid and not member.get("whatsapp_lid"):
            from app.services.database import update_member_lid
            await update_member_lid(member["id"], jid)

        logger.info(f"Fired touchpoint {touchpoint_key} for member {member['id']}")
        return True

    except Exception as e:
        logger.exception(f"Error firing touchpoint {touchpoint_id}: {e}")
        return False


async def escalate_human_touchpoint(touchpoint_id: uuid.UUID) -> bool:
    """Notify the admin number that a member needs manual follow-up."""
    try:
        tp_data = await get_touchpoint_with_member(touchpoint_id)
        if not tp_data:
            logger.error(f"Human touchpoint {touchpoint_id} not found")
            return False

        from app.services.database import get_default_client
        client_data = await get_default_client()
        if not client_data:
            logger.error("No default client found")
            return False

        admin_number = (
            client_data.get("human_escalation_whatsapp")
            or settings.human_escalation_whatsapp
            or ""
        ).strip()
        if not admin_number:
            logger.error("HUMAN_ESCALATION_WHATSAPP is not configured")
            return False

        member = tp_data["member"]
        touchpoint_key = tp_data["touchpoint_key"]
        template = await get_template(client_data["id"], touchpoint_key)
        action = template.get("brief") if template else "Manual action required."
        cta = template.get("cta") if template else ""

        message = _build_human_escalation_message(member, touchpoint_key, action, cta)
        sent, _ = await whatsapp_service.send_message(admin_number, message)
        if not sent:
            logger.error(f"Failed to send human escalation for touchpoint {touchpoint_key}")
            return False

        await update_touchpoint(touchpoint_id, state="needs_human", fired_at=datetime.now(timezone.utc))
        logger.info(f"Human escalation sent for touchpoint {touchpoint_key} member {member['id']}")
        return True

    except Exception as e:
        logger.exception(f"Error escalating human touchpoint {touchpoint_id}: {e}")
        return False


def _build_human_escalation_message(member: Dict[str, Any], touchpoint_key: str, action: str, cta: str) -> str:
    lines = [
        f"Human action needed: {touchpoint_key}",
        "",
        f"Name: {member.get('name') or ''}",
        f"WhatsApp: {member.get('whatsapp') or ''}",
    ]

    optional_fields = [
        ("Email", member.get("email")),
        ("Industry", member.get("industry")),
        ("Company", member.get("company")),
        ("Stage", member.get("stage")),
        ("Building", member.get("building")),
        ("Goals", member.get("goals")),
    ]
    for label, value in optional_fields:
        if value:
            lines.append(f"{label}: {value}")

    lines.extend(["", f"Action: {action}"])
    if cta:
        lines.append(f"CTA: {cta}")

    return "\n".join(lines)


async def fire_nudge(touchpoint_id: uuid.UUID) -> bool:
    """
    Fire a nudge for a silent touchpoint conversation.
    Same pattern as fire_touchpoint but sends a shorter nudge message.
    """
    try:
        tp_data = await get_touchpoint_with_member(touchpoint_id)
        if not tp_data:
            return False

        member = tp_data["member"]
        touchpoint_key = tp_data["touchpoint_key"]

        client_data = None
        from app.services.database import get_default_client
        client_data = await get_default_client()
        if not client_data:
            return False

        template = await get_template(client_data["id"], touchpoint_key)
        if not template and touchpoint_key.startswith(EVENT_REMINDER_PREFIX):
            event_id = touchpoint_key.removeprefix(EVENT_REMINDER_PREFIX)
            try:
                event = await get_event(uuid.UUID(event_id))
            except ValueError:
                event = None
            if event and event["client_id"] == client_data["id"]:
                template = _build_event_template(event)
        if not template or not template.get("active", True):
            logger.info(f"Skipping nudge for {touchpoint_key}: template or event missing/inactive")
            await complete_touchpoint(touchpoint_id)
            return False
        if template:
            template["community_groups"] = await get_groups_for_client(client_data["id"])
            template["community_events"] = await get_upcoming_events_for_client(client_data["id"])

        # Generate nudge via AI
        nudge_text = groq_service.generate_nudge(
            client_data=client_data,
            member=member,
            template=template,
        )

        # Send via WhatsApp
        recipient = member.get("whatsapp_lid") or member.get("whatsapp")
        sent, jid = await whatsapp_service.send_message(recipient, nudge_text)

        if not sent:
            logger.error(f"Failed to send nudge for touchpoint {touchpoint_key}")
            return False

        # Save the nudge message to the conversation
        conversation_id = tp_data.get("conversation_id")
        if conversation_id:
            await save_message(
                conversation_id=conversation_id,
                member_id=member["id"],
                role="agent",
                content=nudge_text,
                touchpoint_key=touchpoint_key,
            )

        # Mark nudge as sent
        await mark_touchpoint_nudged(touchpoint_id)

        logger.info(f"Nudge sent for touchpoint {touchpoint_key} member {member['id']}")
        return True

    except Exception as e:
        logger.exception(f"Error sending nudge for touchpoint {touchpoint_id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# Conditional Logic Checks
# ═══════════════════════════════════════════════════════════

async def _check_conditional(tp_data: Dict[str, Any], tp_def: TouchpointDef) -> bool:
    """
    Check whether a conditional touchpoint should fire.
    Returns True if the condition is met and the touchpoint should proceed.
    """
    touchpoint_key = tp_data["touchpoint_key"]
    member_id = tp_data["member_id"]

    if touchpoint_key == "day_3_no_response":
        # Day 3 follow-up: only fire if there was no reply to Day 1
        return await _has_no_d1_reply(member_id)

    if touchpoint_key == "day_21_yellow_flag":
        # Yellow flag: only fire if engagement_score < threshold
        member = tp_data.get("member", {})
        score = member.get("engagement_score", 1.0)
        return score < settings.engagement_threshold

    if touchpoint_key == "day_21_red_flag":
        # Red flag: requires_human — already handled by requires_human flag
        return True

    if touchpoint_key == "day_35_founder_stories":
        # Conditional on profile — always fire for now (admin can skip in dashboard)
        return True

    # Default: fire
    return True


async def _has_no_d1_reply(member_id: uuid.UUID) -> bool:
    """
    Check if the member has replied to any Day 1 touchpoint.
    Returns True if they haven't (meaning the Day 3 follow-up should fire).
    """
    from app.services.database import get_touchpoints_by_member
    touchpoints = await get_touchpoints_by_member(member_id)

    d1_keys = {"day_1_welcome", "day_1_orientation_checklist"}
    for tp in touchpoints:
        if tp["touchpoint_key"] in d1_keys:
            conv_id = tp.get("conversation_id")
            if conv_id:
                messages = await get_conversation_messages(conv_id)
                has_member_reply = any(msg["role"] == "member" for msg in messages)
                if has_member_reply:
                    return False  # They replied, don't fire Day 3 nudge

    return True  # No reply found, fire the nudge
