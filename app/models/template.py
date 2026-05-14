from sqlalchemy import Column, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    touchpoint_key = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    day = Column(Integer, nullable=True)
    send_time = Column(Text, nullable=True)
    phase = Column(Text, nullable=True)
    automation = Column(Boolean, default=True)
    conditional = Column(Boolean, default=False)
    requires_human = Column(Boolean, default=False)
    purpose = Column(Text, nullable=False)
    cta = Column(Text, nullable=False)
    brief = Column(Text, nullable=False)
    fallback_message = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
