from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///./.pytest-drillloop.db"
os.environ["DEMO_SEED"] = "0"
os.environ["REVIEWER_KEY"] = "test-reviewer"

import pytest
from app.db import engine, init_db
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
