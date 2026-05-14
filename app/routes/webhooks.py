"""
OnboardMe V2 — Webhook Routes

/webhook/onboard  — Client backend fires this on member approval. Creates member, schedules 90-day journey.
/webhook/inbound  — Baileys bridge fires this on incoming WhatsApp messages. Handles conversation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.database import (
    get_client_by_secret,
    get_default_client,
    create_member,
    member_exists,
    find_member_by_whatsapp,
    get_member,
    get_open_conversation,
    create_conversation,
    save_message,
    get_conversation_messages,
    get_template,
    get_touchpoint_by_conversation,
    update_touchpoint,
    complete_touchpoint,
    close_conversation,
    update_member_state,
    update_member_lid,
    get_touchpoints_by_member,
)
from app.services.journey import (
    schedule_journey,
    fire_touchpoint,
    TOUCHPOINT_MAP,
    get_scheduled_touchpoints,
)
from app.services.groq import groq_service
from app.services.whatsapp import whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])


# ═══════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════


class OnboardPayload(BaseModel):
    name: str = Field(..., min_length=1, description="Member's full name")
    whatsapp: str = Field(..., min_length=1, description="WhatsApp number in international format without +, e.g. 2348012345678")
    email: Optional[str] = None
    industry: Optional[str] = None
    company: Optional[str] = None
    stage: Optional[str] = None
    building: Optional[str] = None
    focus_areas: Optional[List[str]] = None
    why_community: Optional[str] = None
    goals: Optional[str] = None
    revenue_range: Optional[str] = None
    approved_at: Optional[str] = None


class InboundPayload(BaseModel):
    whatsapp: str = Field(..., description="WhatsApp number from the bridge")
    message: str = Field(..., description="Message text content")
    jid: Optional[str] = Field(None, description="JID or LID from Baileys bridge")


# ═══════════════════════════════════════════════════════════
# Onboard — Start a member's 90-day journey
# ═══════════════════════════════════════════════════════════


@router.post("/onboard")
async def handle_onboard(
    payload: OnboardPayload,
    x_webhook_secret: Optional[str] = Header(None),
):
    """
    Triggered by client backend when a member is approved.
    Creates member record, schedules all 90-day touchpoints, fires Day 1 immediately.
    """
    try:
        # 1. Verify webhook secret
        if not x_webhook_secret:
            raise HTTPException(status_code=401, detail="Missing X-Webhook-Secret header")

        client = await get_client_by_secret(x_webhook_secret)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        client_id = client["id"]

        # 2. Validate required fields
        if not payload.name or not payload.name.strip():
            raise HTTPException(status_code=422, detail="Missing required field: name")
        if not payload.whatsapp or not payload.whatsapp.strip():
            raise HTTPException(status_code=422, detail="Missing required field: whatsapp")

        # Normalize whatsapp: strip +, spaces, dashes, convert to international format
        raw_whatsapp = payload.whatsapp.strip().replace(" ", "").replace("-", "").replace("+", "")
        if raw_whatsapp.startswith("0") and len(raw_whatsapp) == 11:
            # Nigerian local format (09167659790) → international (2349167659790)
            raw_whatsapp = "234" + raw_whatsapp[1:]

        # 3. Check for duplicate active member
        exists = await member_exists(raw_whatsapp, client_id)
        if exists:
            logger.warning(f"Member with whatsapp {raw_whatsapp} already has an active journey")
            raise HTTPException(
                status_code=409,
                detail="Member already has an active journey. Resubmit not allowed.",
            )

        # 4. Parse approved_at
        approved_at = None
        if payload.approved_at:
            try:
                approved_at = datetime.fromisoformat(payload.approved_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                approved_at = datetime.now(timezone.utc)
        else:
            approved_at = datetime.now(timezone.utc)

        # 5. Create member record
        member = await create_member(
            client_id=client_id,
            name=payload.name.strip(),
            whatsapp=raw_whatsapp,
            email=payload.email,
            industry=payload.industry,
            company=payload.company,
            stage=payload.stage,
            building=payload.building,
            focus_areas=payload.focus_areas,
            why_community=payload.why_community,
            goals=payload.goals,
            revenue_range=payload.revenue_range,
            approved_at=approved_at,
        )
        member_id = member["id"]
        logger.info(f"Created member {member_id} for {payload.name} ({raw_whatsapp})")

        # 6. Schedule all 90-day touchpoints
        touchpoint_count = await schedule_journey(member_id, approved_at, client_id)
        logger.info(f"Scheduled {touchpoint_count} touchpoints for member {member_id}")

        # 7. Fire Day 1 Welcome immediately
        day1_touchpoints = await get_touchpoints_by_member(member_id)
        fired_count = 0
        for tp in day1_touchpoints:
            if tp["touchpoint_key"] == "day_1_welcome" and tp["state"] == "pending":
                success = await fire_touchpoint(tp["id"])
                if success:
                    fired_count += 1

        logger.info(f"Fired {fired_count} Day 1 touchpoints for member {member_id}")

        # 8. If no Day 1 touchpoint fired successfully (e.g. WhatsApp send failed),
        #    the member is created but journey starts when fire-touchpoints cron picks up
        return {
            "status": "success",
            "member_id": str(member_id),
            "touchpoints_scheduled": touchpoint_count,
            "day1_fired": fired_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in handle_onboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Inbound — Handle incoming WhatsApp messages
# ═══════════════════════════════════════════════════════════


@router.post("/inbound")
async def handle_inbound(data: dict):
    """
    Receives incoming WhatsApp messages from the Baileys bridge.
    Finds or creates conversation, saves message, calls AI, sends response.
    """
    logger.debug(f"Received inbound data keys: {list(data.keys())}")

    try:
        raw_phone = data.get("whatsapp", "").strip()
        user_message = data.get("message", "").strip()
        jid = data.get("jid", "").strip()

        # Ignore status broadcasts
        if jid == "status@broadcast":
            logger.debug("Ignoring status broadcast")
            return {"status": "ignored", "reason": "Status broadcast"}

        if not user_message:
            logger.debug("Empty message received, ignoring")
            return {"status": "ignored", "reason": "Empty message"}

        # ─── Step 1: Find member ───
        # Priority: LID match first (most reliable from bridge), then phone fallbacks
        member = None
        lookup_method = None

        if jid and "@lid" in jid:
            lid_number = jid.replace("@lid", "")
            member = await find_member_by_whatsapp(lid_number)
            if member:
                lookup_method = f"lid:{lid_number}"

        if not member and jid and "@s.whatsapp.net" in jid:
            jid_number = jid.replace("@s.whatsapp.net", "")
            member = await find_member_by_whatsapp(jid_number)
            if member:
                lookup_method = f"jid:{jid_number}"

        if not member:
            member = await find_member_by_whatsapp(raw_phone)
            if member:
                lookup_method = f"phone:{raw_phone}"

        if not member:
            logger.warning(f"No member found for whatsapp={raw_phone}, jid={jid}")
            return {"status": "ignored", "reason": "No member found"}

        member_id = member["id"]
        logger.info(f"Matched member {member_id} via {lookup_method}")

        # ─── Step 2: Link LID if we don't have it yet ───
        if jid and not member.get("whatsapp_lid"):
            logger.debug(f"Linking JID {jid} to member {member_id}")
            await update_member_lid(member_id, jid)

        # ─── Step 3: Ignore completed/churned members ───
        if member["state"] in ("completed", "churned"):
            logger.debug(f"Member {member_id} state is '{member['state']}', ignoring message")
            return {"status": "ignored", "reason": f"Member {member['state']}"}

        # ─── Step 4: Find or create conversation ───
        conv = await get_open_conversation(member_id)

        # If no open conversation exists, create one for free-form inbound
        touchpoint_key = None
        if not conv:
            # Check if there's a pending touchpoint that should have been fired
            # This can happen if the member messages before the cron picks up
            touchpoints = await get_touchpoints_by_member(member_id)
            pending_tp = next(
                (tp for tp in touchpoints if tp["state"] == "pending"), None
            )
            if pending_tp:
                # Fire this touchpoint now
                from app.services.journey import fire_touchpoint
                await fire_touchpoint(pending_tp["id"])
                conv = await get_open_conversation(member_id)

            if not conv:
                # Truly free-form — create an open conversation without a touchpoint
                conv = await create_conversation(member_id)
                logger.info(f"Created free-form conversation {conv['id']} for member {member_id}")

        conversation_id = conv["id"]
        touchpoint_key = conv.get("touchpoint_key")

        # ─── Step 5: Save member message to DB FIRST ───
        await save_message(
            conversation_id=conversation_id,
            member_id=member_id,
            role="member",
            content=user_message,
            touchpoint_key=touchpoint_key,
        )
        logger.debug(f"Saved member message for conversation {conversation_id}")

        # ─── Step 6: Update member state if pending → active ───
        if member["state"] == "pending":
            await update_member_state(member_id, state="active")

        # ─── Step 7: Load full conversation history ───
        messages = await get_conversation_messages(conversation_id)
        logger.debug(f"Loaded {len(messages)} messages for conversation {conversation_id}")

        # ─── Step 8: Get client and template context ───
        client = await get_default_client()
        if not client:
            logger.error("No default client configured")
            raise HTTPException(status_code=500, detail="No client configured")

        template = None
        if touchpoint_key:
            template = await get_template(client["id"], touchpoint_key)

        # ─── Step 9: Get fresh member profile ───
        member_profile = await get_member(member_id)
        if not member_profile:
            logger.error(f"Member {member_id} not found after creation")
            raise HTTPException(status_code=500, detail="Member not found")

        # ─── Step 10: Call AI to generate response ───
        response_text = groq_service.generate_response(
            client_data=client,
            member=member_profile,
            messages=messages,
            template=template,
        )

        # ─── Step 11: Save agent response ───
        await save_message(
            conversation_id=conversation_id,
            member_id=member_id,
            role="agent",
            content=response_text,
            touchpoint_key=touchpoint_key,
        )

        # ─── Step 12: Send via WhatsApp ───
        recipient = member.get("whatsapp_lid") or member.get("whatsapp")
        logger.info(f"Sending response to {recipient}")
        sent, final_jid = await whatsapp_service.send_message(recipient, response_text)

        if not sent:
            logger.error(f"Failed to send response to {recipient}")
            # Don't raise — message is saved, delivery failure shouldn't 500 the webhook

        # Update LID if bridge returned a new one
        if final_jid and final_jid != recipient:
            await update_member_lid(member_id, final_jid)

        # ─── Step 13: Check for CTA completion ───
        if template and touchpoint_key:
            cta_delivered = _detect_cta_completion(response_text, template, touchpoint_key)
            if cta_delivered:
                tp = await get_touchpoint_by_conversation(conversation_id)
                if tp and tp["state"] == "in_conversation":
                    logger.info(f"CTA delivered — completing touchpoint {tp['id']} ({touchpoint_key})")
                    await complete_touchpoint(tp["id"])
                    await close_conversation(conversation_id)

        # ─── Step 14: Update engagement score (simple version) ───
        await _update_engagement(member_id)

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in handle_inbound: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# CTA Detection & Engagement Scoring
# ═══════════════════════════════════════════════════════════


def _detect_cta_completion(
    agent_response: str,
    template: dict,
    touchpoint_key: str,
) -> bool:
    """
    Detect whether the AI's response indicates the CTA has been delivered
    and the touchpoint should close.

    A touchpoint closes when:
    - The invite link has been shared (for day_14, day_1)
    - A booking link has been shared (for day_9, day_60)
    - The member has given a clear answer and the AI has acknowledged it warmly
      and signalled closure (for day_7, day_5, day_28, etc.)
    """
    # Check if invite link was shared
    from app.config import settings
    if settings.invite_link and settings.invite_link in agent_response:
        return True

    # Check for closing signals in the AI response
    closing_phrases = [
        "talk soon",
        "chat later",
        "have a good",
        "catch you later",
        "great having",
        "glad you're here",
        "welcome to the community",
        "see you around",
        "that's all for now",
        "enjoy the rest of your",
    ]

    response_lower = agent_response.lower()
    for phrase in closing_phrases:
        if phrase in response_lower:
            return True

    # Don't close too aggressively — only if the AI has clearly wrapped up
    return False


async def _update_engagement(member_id: UUID):
    """
    Simple engagement score update.
    Score = ratio of conversations where member has replied vs total conversations.
    Called after every member message.
    """
    try:
        touchpoints = await get_touchpoints_by_member(member_id)
        total = len(touchpoints)
        if total == 0:
            return

        # Count touchpoints where the member has engaged
        engaged = 0
        for tp in touchpoints:
            conv_id = tp.get("conversation_id")
            if conv_id:
                msgs = await get_conversation_messages(conv_id)
                has_reply = any(m["role"] == "member" for m in msgs)
                if has_reply:
                    engaged += 1

        score = round(engaged / total, 2)
        await update_member_state(member_id, state=None, engagement_score=score)
        logger.debug(f"Updated engagement score for {member_id}: {score}")

    except Exception as e:
        logger.debug(f"Failed to update engagement score: {e}")
