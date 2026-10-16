import logging
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger("certificate-database")

engine_kwargs = {"pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    engine_kwargs["pool_size"] = settings.db_pool_size
    engine_kwargs["max_overflow"] = settings.db_max_overflow

engine = create_engine(settings.database_url, **engine_kwargs)
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
    try:
        Base.metadata.create_all(bind=engine, tables=tables)
    except (IntegrityError, DBAPIError) as exc:
        err_msg = str(exc).lower()
        if "already exists" in err_msg or "pg_type_typname_nsp_index" in err_msg:
            logger.info("Concurrent init_db: tables/types already created by peer process.")
        else:
            raise
