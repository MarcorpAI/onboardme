from sqlalchemy import Column, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class JourneyTouchpoint(Base):
    __tablename__ = "journey_touchpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    touchpoint_key = Column(Text, nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    fired_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    state = Column(Text, default="pending")
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    requires_human = Column(Boolean, default=False)
    nudge_sent = Column(Boolean, default=False)
