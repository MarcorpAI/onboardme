from sqlalchemy import Column, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    community_name = Column(Text, nullable=False)
    community_description = Column(Text, nullable=True)
    agent_name = Column(Text, nullable=False)
    agent_tone = Column(Text, default="warm and conversational")
    webhook_secret = Column(Text, nullable=False)
    invite_link = Column(Text, nullable=True)
    calendly_link = Column(Text, nullable=True)
    founder_stories_link = Column(Text, nullable=True)
    operator_session_link = Column(Text, nullable=True)
    human_escalation_whatsapp = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
