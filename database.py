# database.py — ParkWise Nairobi
# DatabasePool class manages the asyncpg connection pool lifecycle.
# Imported by main.py and injected into route handlers via FastAPI's Depends().

import os
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI


class DatabasePool:
    """Manages the asyncpg connection pool for the ParkWise FastAPI backend."""

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._dsn = self._resolve_dsn()

    # ── Setup ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_dsn() -> str:
        """Read DATABASE_URL from environment and normalise the scheme."""
        url = os.environ.get("DATABASE_URL", "")
        # Render sets postgres:// but asyncpg requires postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    async def connect(self) -> None:
        """Open the connection pool. Called once on app startup."""
        if not self._dsn:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close the connection pool. Called once on app shutdown."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ── Access ────────────────────────────────────────────────────────────────

    def get_pool(self) -> asyncpg.Pool:
        """Return the live pool. Raises if connect() has not been called."""
        if self._pool is None:
            raise RuntimeError("Database pool is not initialised.")
        return self._pool

    # ── FastAPI lifespan integration ──────────────────────────────────────────

    def lifespan(self, app: FastAPI):
        """
        AsyncContextManager for FastAPI lifespan events.

        Usage in main.py:
            db = DatabasePool()

            @asynccontextmanager
            async def lifespan(app):
                async with db.lifespan(app):
                    yield

            app = FastAPI(lifespan=lifespan)
        """
        return self._lifespan_cm(app)

    @asynccontextmanager
    async def _lifespan_cm(self, app: FastAPI):
        await self.connect()
        try:
            yield
        finally:
            await self.disconnect()


# ── Shared singleton ──────────────────────────────────────────────────────────
# Import `db` everywhere; call db.get_pool() inside route handlers.
db = DatabasePool()


def get_pool() -> asyncpg.Pool:
    """FastAPI dependency — inject with Depends(get_pool)."""
    return db.get_pool()
