from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    tables = None
    if not settings.enable_khp_master_staging:
        tables = [
            table
            for name, table in Base.metadata.tables.items()
            if name != "khp_master_resolutions"
        ]
    Base.metadata.create_all(bind=engine, tables=tables)
