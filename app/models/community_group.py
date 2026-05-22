from sqlalchemy import Column, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class CommunityGroup(Base):
    __tablename__ = "community_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    purpose = Column(Text, nullable=True)
    link = Column(Text, nullable=True)
    activity_day = Column(Text, nullable=True)
    cta_guidance = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
