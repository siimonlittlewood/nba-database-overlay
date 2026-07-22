from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.config import get_settings

engine = create_engine(get_settings().database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
