from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./drillloop.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    source_columns = {column["name"] for column in inspect(engine).get_columns("sources")}
    if "source_bytes" not in source_columns:
        binary_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE sources ADD COLUMN source_bytes {binary_type}"))


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
