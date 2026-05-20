"""
OnboardMe V2 — Cron Job Routes

Jobs triggered by external cron scheduler (or APScheduler):

/jobs/fire-touchpoints    — Every 5 min: fire pending touchpoints past their scheduled time
/jobs/nudge-silent        — Every 15 min: nudge silent in-conversation touchpoints
/jobs/timeout-touchpoints — Every hour: timeout conversations silent for 24h
/jobs/flag-disengaged     — Daily: flag low-engagement members for human review
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.services.database import (
    get_pending_touchpoints,
    get_pending_human_touchpoints,
    get_touchpoints_needing_nudge,
    get_timed_out_touchpoints,
    get_disengaged_members,
    get_default_client,
    get_template,
    update_touchpoint,
    complete_touchpoint,
    close_conversation,
    update_member_state,
    insert_touchpoint,
    get_touchpoints_by_member,
)
from app.services.journey import (
    fire_touchpoint,
    escalate_human_touchpoint,
    fire_nudge,
    TOUCHPOINT_MAP,
    can_fire_touchpoint,
)
from app.services.whatsapp import whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/fire-touchpoints")
async def fire_pending_touchpoints():
    """
    Finds all pending touchpoints past their scheduled_for time and fires them.
    Runs every 5 minutes.
    Skips:
    - requires_human touchpoints (handled via dashboard)
    - conditional touchpoints whose conditions aren't met (checked inside fire_touchpoint)
    """
    pending = await get_pending_touchpoints()
    pending_human = await get_pending_human_touchpoints()
    logger.info(f"Found {len(pending)} pending touchpoints and {len(pending_human)} human touchpoints to process")

    client = await get_default_client()
    if not client:
        logger.error("No default client found — cannot process touchpoints")
        return {"error": "No client configured"}

    results = []
    for tp in pending_human:
        template = await get_template(client["id"], tp["touchpoint_key"])
        if not template or not template.get("active"):
            await complete_touchpoint(tp["id"])
            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "skipped",
                "reason": "template missing or inactive",
            })
            continue

        eligible, reason = await can_fire_touchpoint(tp)
        if not eligible:
            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "deferred",
                "reason": reason,
            })
            continue

        success = await escalate_human_touchpoint(tp["id"])
        results.append({
            "touchpoint_id": str(tp["id"]),
            "touchpoint_key": tp["touchpoint_key"],
            "member_id": str(tp["member_id"]),
            "status": "escalated" if success else "failed",
        })

    for tp in pending:
        template = await get_template(client["id"], tp["touchpoint_key"])
        if not template or not template.get("active"):
            await complete_touchpoint(tp["id"])
            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "skipped",
                "reason": "template missing or inactive",
            })
            continue

        eligible, reason = await can_fire_touchpoint(tp)
        if not eligible:
            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "deferred",
                "reason": reason,
            })
            continue

        success = await fire_touchpoint(tp["id"])
        results.append({
            "touchpoint_id": str(tp["id"]),
            "touchpoint_key": tp["touchpoint_key"],
            "member_id": str(tp["member_id"]),
            "status": "fired" if success else "failed",
        })

    fired = sum(1 for r in results if r["status"] == "fired")
    escalated = sum(1 for r in results if r["status"] == "escalated")
    deferred = sum(1 for r in results if r["status"] == "deferred")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")

    logger.info(f"fire-touchpoints: {fired} fired, {escalated} escalated, {deferred} deferred, {skipped} skipped, {failed} failed")

    return {
        "processed": len(pending) + len(pending_human),
        "fired": fired,
        "escalated": escalated,
        "deferred": deferred,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


@router.post("/nudge-silent")
async def nudge_silent_conversations():
    """
    Finds touchpoints in 'in_conversation' state with no member reply
    in the configured nudge_delay_mins and nudge_sent = False.
    Sends a short AI-generated nudge.
    Runs every 15 minutes.
    """
    delay_mins = settings.nudge_delay_mins
    needing_nudge = await get_touchpoints_needing_nudge(delay_mins)
    logger.info(f"Found {len(needing_nudge)} touchpoints needing nudge")

    results = []
    for tp in needing_nudge:
        success = await fire_nudge(tp["id"])
        results.append({
            "touchpoint_id": str(tp["id"]),
            "touchpoint_key": tp["touchpoint_key"],
            "member_id": str(tp["member_id"]),
            "status": "nudged" if success else "failed",
        })

    nudged = sum(1 for r in results if r["status"] == "nudged")
    failed = sum(1 for r in results if r["status"] == "failed")

    logger.info(f"nudge-silent: {nudged} nudged, {failed} failed out of {len(needing_nudge)}")

    return {
        "processed": len(needing_nudge),
        "nudged": nudged,
        "failed": failed,
        "results": results,
    }


@router.post("/timeout-touchpoints")
async def timeout_stale_touchpoints():
    """
    Finds touchpoints in 'in_conversation' state with no member activity
    in the configured timeout_hours. Marks them completed and closes the conversation.
    Runs every hour.
    """
    hours = settings.timeout_hours
    timed_out = await get_timed_out_touchpoints(hours)
    logger.info(f"Found {len(timed_out)} timed-out touchpoints to close")

    results = []
    for tp in timed_out:
        try:
            # Close the conversation if it exists
            conv_id = tp.get("conversation_id")
            if conv_id:
                await close_conversation(conv_id)

            # Mark touchpoint as completed (timed out)
            await complete_touchpoint(tp["id"])

            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "timed_out",
            })
        except Exception as e:
            logger.error(f"Failed to timeout touchpoint {tp['id']}: {e}")
            results.append({
                "touchpoint_id": str(tp["id"]),
                "touchpoint_key": tp["touchpoint_key"],
                "member_id": str(tp["member_id"]),
                "status": "failed",
            })

    timed_out_count = sum(1 for r in results if r["status"] == "timed_out")
    logger.info(f"timeout-touchpoints: {timed_out_count} timed out of {len(timed_out)}")

    return {
        "processed": len(timed_out),
        "timed_out": timed_out_count,
        "results": results,
    }


@router.post("/flag-disengaged")
async def flag_disengaged_members():
    """
    Finds members with engagement_score < threshold who have been active
    for at least engagement_days. Creates a requires_human touchpoint
    flagged for admin review in the dashboard.
    Runs daily.
    """
    client = await get_default_client()
    if not client:
        logger.error("No default client found — cannot flag disengaged members")
        return {"error": "No client configured"}

    disengaged = await get_disengaged_members(
        threshold=settings.engagement_threshold,
        min_days=settings.engagement_days,
        client_id=client["id"],
    )
    logger.info(f"Found {len(disengaged)} disengaged members to flag")

    results = []
    for member in disengaged:
        try:
            member_id = member["id"]

            # Check if there's already a pending human flag for this member
            existing = await get_touchpoints_by_member(member_id)
            already_flagged = any(
                tp["touchpoint_key"] == "day_21_red_flag" and tp["state"] == "pending"
                for tp in existing
            )

            if already_flagged:
                logger.debug(f"Member {member_id} already has pending red flag, skipping")
                results.append({
                    "member_id": str(member_id),
                    "status": "already_flagged",
                })
                continue

            # Create a requires_human touchpoint for admin review
            from datetime import timedelta, timezone
            from app.services.database import insert_touchpoint

            await insert_touchpoint(
                member_id=member_id,
                touchpoint_key="day_21_red_flag",
                scheduled_for=datetime.now(timezone.utc),
                requires_human=True,
            )

            results.append({
                "member_id": str(member_id),
                "status": "flagged",
            })

        except Exception as e:
            logger.error(f"Failed to flag member {member['id']}: {e}")
            results.append({
                "member_id": str(member["id"]),
                "status": "failed",
            })

    flagged = sum(1 for r in results if r["status"] == "flagged")
    logger.info(f"flag-disengaged: {flagged} flagged out of {len(disengaged)}")

    return {
        "processed": len(disengaged),
        "flagged": flagged,
        "already_flagged": sum(1 for r in results if r["status"] == "already_flagged"),
        "results": results,
    }
