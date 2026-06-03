import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from app.config import settings
from app.services.database import (
    create_broadcast,
    get_approved_members,
    get_broadcast,
    get_broadcast_recipients,
    get_next_broadcast_to_send,
    mark_broadcast_completed_if_done,
    mark_broadcast_recipient_failed,
    mark_broadcast_recipient_sent,
    mark_broadcast_sending,
    queue_broadcast,
    create_conversation,
    get_open_conversation,
    save_message,
)
from app.services.whatsapp import whatsapp_service

logger = logging.getLogger(__name__)

BROADCAST_TOUCHPOINT_PREFIX = "broadcast:"


def normalize_broadcast_number(value: str) -> Optional[str]:
    """Normalize a WhatsApp number to digits without '+', biased for Nigerian local numbers."""
    digits = re.sub(r"\D+", "", value or "")
    if not digits:
        return None
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    elif len(digits) == 10 and not digits.startswith("0"):
        digits = "234" + digits
    if not 10 <= len(digits) <= 15:
        return None
    return digits


def parse_manual_numbers(raw: str) -> tuple[List[str], List[str]]:
    numbers = []
    invalid = []
    seen = set()
    for item in re.split(r"[\n,;]+", raw or ""):
        original = item.strip()
        if not original:
            continue
        normalized = normalize_broadcast_number(original)
        if not normalized:
            invalid.append(original)
            continue
        if normalized not in seen:
            seen.add(normalized)
            numbers.append(normalized)
    return numbers, invalid


def build_broadcast_recipients(
    approved_members: List[Dict[str, Any]],
    manual_numbers: List[str],
    include_approved_members: bool,
) -> List[Dict[str, Any]]:
    recipients_by_number: Dict[str, Dict[str, Any]] = {}

    if include_approved_members:
        for member in approved_members:
            normalized = normalize_broadcast_number(member.get("whatsapp") or "")
            if not normalized:
                continue
            recipients_by_number[normalized] = {
                "whatsapp": normalized,
                "member_id": member["id"],
                "source": "member",
            }

    for number in manual_numbers:
        recipients_by_number.setdefault(number, {
            "whatsapp": number,
            "member_id": None,
            "source": "manual",
        })

    return list(recipients_by_number.values())


async def create_broadcast_draft(
    client_data: Dict[str, Any],
    title: str,
    message: str,
    brief: Optional[str],
    manual_numbers_raw: str,
    include_approved_members: bool,
) -> Dict[str, Any]:
    manual_numbers, invalid_numbers = parse_manual_numbers(manual_numbers_raw)
    approved_members = await get_approved_members(client_data["id"]) if include_approved_members else []
    recipients = build_broadcast_recipients(approved_members, manual_numbers, include_approved_members)

    if not recipients:
        raise ValueError("No valid recipients selected")
    if len(recipients) > settings.broadcast_max_recipients:
        raise ValueError(f"Broadcast recipient limit is {settings.broadcast_max_recipients}")

    broadcast = await create_broadcast(
        client_id=client_data["id"],
        title=title,
        brief=brief,
        message=message,
        recipients=recipients,
        include_approved_members=include_approved_members,
    )
    broadcast["invalid_numbers"] = invalid_numbers
    return broadcast


async def queue_existing_broadcast(broadcast_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    return await queue_broadcast(broadcast_id)


async def process_broadcast_queue() -> Dict[str, Any]:
    """Send a small batch from the oldest queued broadcast."""
    broadcast = await get_next_broadcast_to_send()
    if not broadcast:
        return {"broadcast_id": None, "processed": 0, "sent": 0, "failed": 0}

    await mark_broadcast_sending(broadcast["id"])
    if not await whatsapp_service.is_connected():
        logger.warning("Broadcast %s is queued but WhatsApp bridge is not connected", broadcast["id"])
        return {
            "broadcast_id": str(broadcast["id"]),
            "status": "waiting_for_whatsapp",
            "processed": 0,
            "sent": 0,
            "failed": 0,
        }

    recipients = await get_broadcast_recipients(
        broadcast["id"],
        limit=max(settings.broadcast_batch_size, 1),
        statuses=["pending"],
    )
    if not recipients:
        updated = await mark_broadcast_completed_if_done(broadcast["id"])
        return {
            "broadcast_id": str(broadcast["id"]),
            "status": updated.get("status") if updated else broadcast["status"],
            "processed": 0,
            "sent": 0,
            "failed": 0,
        }

    delay = 60 / max(settings.broadcast_messages_per_minute, 1)
    sent_count = 0
    failed_count = 0
    for index, recipient in enumerate(recipients):
        sent, _ = await whatsapp_service.send_message(recipient["whatsapp"], broadcast["message"])
        if sent:
            await mark_broadcast_recipient_sent(recipient["id"])
            sent_count += 1
            if recipient.get("member_id"):
                await _save_member_broadcast_message(
                    member_id=recipient["member_id"],
                    broadcast_id=broadcast["id"],
                    message=broadcast["message"],
                )
        else:
            await mark_broadcast_recipient_failed(
                recipient["id"],
                "WhatsApp bridge send failed",
                max(settings.broadcast_retry_limit, 1),
            )
            failed_count += 1

        if index < len(recipients) - 1:
            await asyncio.sleep(delay)

    updated = await mark_broadcast_completed_if_done(broadcast["id"])
    return {
        "broadcast_id": str(broadcast["id"]),
        "status": updated.get("status") if updated else "sending",
        "processed": len(recipients),
        "sent": sent_count,
        "failed": failed_count,
    }


async def _save_member_broadcast_message(member_id: uuid.UUID, broadcast_id: uuid.UUID, message: str):
    conversation = await get_open_conversation(member_id)
    if not conversation:
        conversation = await create_conversation(member_id, f"{BROADCAST_TOUCHPOINT_PREFIX}{broadcast_id}")
    await save_message(
        conversation_id=conversation["id"],
        member_id=member_id,
        role="agent",
        content=message,
        touchpoint_key=f"{BROADCAST_TOUCHPOINT_PREFIX}{broadcast_id}",
    )
