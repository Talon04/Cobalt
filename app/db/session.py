from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.db import Base

engine = create_engine(settings.database_url, echo=settings.sqlalchemy_echo)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Create tables"""
    Base.metadata.create_all(bind=engine)

def get_db_session():
    return SessionLocal()
