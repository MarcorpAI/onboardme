"""
SQLAlchemy Base — shared declarative base for all models.
Defined in a separate module to avoid circular imports between
models (which import Base) and services/database.py (which uses model classes).
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
