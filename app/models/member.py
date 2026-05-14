from sqlalchemy import Column, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class Member(Base):
    __tablename__ = "members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    whatsapp = Column(Text, nullable=False)
    whatsapp_lid = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    industry = Column(Text, nullable=True)
    company = Column(Text, nullable=True)
    stage = Column(Text, nullable=True)
    building = Column(Text, nullable=True)
    focus_areas = Column(ARRAY(Text), nullable=True)
    why_community = Column(Text, nullable=True)
    goals = Column(Text, nullable=True)
    revenue_range = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_source = Column(Text, default="webhook")
    journey_day = Column(Integer, default=0)
    journey_phase = Column(Text, default="foundation")
    engagement_score = Column(Float, default=0.0)
    state = Column(Text, default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_active_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
