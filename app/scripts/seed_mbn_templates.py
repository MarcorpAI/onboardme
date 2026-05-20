"""Seed MBN WhatsApp onboarding templates into the configured database."""

import argparse
import asyncio
import socket
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.data.mbn_templates import MBN_TEMPLATES, validate_mbn_templates
from app.services.database import (
    delete_templates_for_client,
    get_default_client,
    get_templates_for_client,
    init_db,
    upsert_default_client,
    upsert_template,
)


SYNC_FIELDS = (
    "name",
    "day",
    "send_time",
    "phase",
    "automation",
    "conditional",
    "requires_human",
    "purpose",
    "cta",
    "brief",
    "fallback_message",
    "active",
)


def _diff(existing: dict[str, Any] | None, template: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    if existing is None:
        return {field: (None, template.get(field)) for field in SYNC_FIELDS}

    changes = {}
    for field in SYNC_FIELDS:
        current = existing.get(field)
        desired = template.get(field)
        if current != desired:
            changes[field] = (current, desired)
    return changes


async def seed_templates(apply: bool, reset: bool = False) -> int:
    validate_mbn_templates()

    try:
        if apply or reset:
            await init_db()
            client = await upsert_default_client()
        else:
            client = await get_default_client()
            if not client:
                print("No default client exists. Run with --apply after configuring .env to create/sync it.")
                return 1
    except (OSError, socket.gaierror, SQLAlchemyError) as exc:
        target = "DATABASE_URL" if settings.database_url else "POSTGRES_HOST/POSTGRES_PORT"
        print(f"Database connection failed using {target}: {exc}")
        if not settings.database_url:
            print("Set DATABASE_URL in .env for Neon, including sslmode=require if Neon requires SSL.")
        return 1

    client_id = client["id"]
    existing_templates = await get_templates_for_client(client_id, include_inactive=True)
    existing_by_key = {template["touchpoint_key"]: template for template in existing_templates}

    if reset:
        print(f"reset: deleting {len(existing_templates)} existing templates for default client")
        deleted = await delete_templates_for_client(client_id)
        print(f"reset: deleted {deleted} templates")
        existing_templates = []
        existing_by_key = {}

    created = 0
    updated = 0
    unchanged = 0

    for template in MBN_TEMPLATES:
        key = template["touchpoint_key"]
        existing = existing_by_key.get(key)
        changes = _diff(existing, template)

        if not changes:
            unchanged += 1
            continue

        if existing:
            updated += 1
            action = "update"
        else:
            created += 1
            action = "create"

        changed_fields = ", ".join(changes.keys())
        print(f"{action}: {key} ({changed_fields})")

        if apply or reset:
            await upsert_template(
                client_id=client_id,
                touchpoint_key=key,
                name=template["name"],
                day=template["day"],
                send_time=template["send_time"],
                phase=template["phase"],
                automation=template["automation"],
                conditional=template["conditional"],
                requires_human=template["requires_human"],
                purpose=template["purpose"],
                cta=template["cta"],
                brief=template["brief"],
                fallback_message=template["fallback_message"],
                active=template["active"],
            )

    mode = "reset-applied" if reset else "applied" if apply else "dry-run"
    print(
        f"MBN template seed {mode}: {created} to create, "
        f"{updated} to update, {unchanged} unchanged."
    )

    if apply or reset:
        inactive_keys = sorted(template["touchpoint_key"] for template in MBN_TEMPLATES if not template["active"])
        if inactive_keys:
            print("Inactive MBN templates will be skipped by the scheduler:")
            for key in inactive_keys:
                print(f"- {key}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show changes without writing to the database.")
    mode.add_argument("--apply", action="store_true", help="Upsert MBN templates into the database.")
    mode.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing templates for the default client, then seed only the MBN templates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(seed_templates(apply=args.apply, reset=args.reset)))


if __name__ == "__main__":
    main()
