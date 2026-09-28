"""Test fixtures: a throwaway PostgreSQL 16 in Docker, migrated with Alembic.

HTTP tests get `client`, an httpx client on the real app sharing the test's
session; the clock is a mutable holder so a test can move time.
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from app.models import Child, Parent
from tests.helpers import at

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONTENT_DIR = BACKEND_DIR.parent / "content"  # tests count topics and words from the YAML
BOT_API_TOKEN = "test-bot-token"
ADMIN_API_TOKEN = "test-admin-token"
DAY1 = date(2026, 9, 22)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        # Settings (and therefore Alembic env.py) read DATABASE_URL from the environment.
        os.environ["DATABASE_URL"] = url
        os.environ["BOT_API_TOKEN"] = BOT_API_TOKEN
        os.environ["ADMIN_API_TOKEN"] = ADMIN_API_TOKEN
        from app.core.config import get_settings

        get_settings.cache_clear()
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        yield url


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def seeded(engine: AsyncEngine) -> None:
    """Both topics loaded once per test session (seeding is idempotent)."""
    from app.seed import load_topics, seed_topics

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await seed_topics(session, load_topics(CONTENT_DIR))


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
async def child(db: AsyncSession, seeded: None) -> Child:
    """A fresh child with default settings; each test gets its own so state never leaks."""
    child = Child(name="Сандро")
    db.add(child)
    await db.flush()
    return child


@pytest.fixture
async def parent(db: AsyncSession, child: Child) -> Parent:
    parent = Parent(telegram_id=1000 + child.id, name="Папа")
    parent.children.append(child)
    db.add(parent)
    await db.flush()
    return parent


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment


@pytest.fixture
def clock() -> Clock:
    return Clock(at(DAY1))


@pytest.fixture
async def client(db: AsyncSession, clock: Clock) -> AsyncIterator[AsyncClient]:
    from app.api.deps import get_db, get_now
    from app.main import create_app

    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_now] = lambda: clock.moment
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
