from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (registers tables)
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        # Supabase exposes the public schema through its auto-generated REST API. Turning on Row Level
        # Security with no policies means the anon/authenticated keys can't read these tables directly;
        # only this backend (direct Postgres connection) can. All access goes through our API checks.
        from sqlalchemy import text
        with engine.begin() as conn:
            for table in Base.metadata.tables:
                conn.execute(text(f'alter table public."{table}" enable row level security'))
