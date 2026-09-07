# database.py — ParkWise Nairobi
# DatabasePool class manages psycopg2 connections.
# Switched from asyncpg to psycopg2-binary for Python 3.14 compatibility.

import os
import psycopg2
import psycopg2.extras
from contextlib import asynccontextmanager
from fastapi import FastAPI


class DatabasePool:
    """Manages psycopg2 connections for the ParkWise FastAPI backend."""

    def __init__(self):
        self._dsn = self._resolve_dsn()

    # ── Setup ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_dsn() -> str:
        """Read DATABASE_URL from environment and normalise the scheme."""
        url = os.environ.get("DATABASE_URL", "")
        # Ensure postgresql:// scheme
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    async def connect(self) -> None:
        """Validate DSN on startup."""
        if not self._dsn:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        print("[database] DATABASE_URL is set — psycopg2 ready.")

    async def disconnect(self) -> None:
        """No persistent pool to close with psycopg2."""
        print("[database] Shutdown complete.")

    # ── Access ────────────────────────────────────────────────────────────────

    def get_connection(self):
        """Open and return a new psycopg2 connection."""
        if not self._dsn:
            raise RuntimeError("DATABASE_URL is not set.")
        return psycopg2.connect(self._dsn)

    # ── FastAPI lifespan integration ──────────────────────────────────────────

    @asynccontextmanager
    async def _lifespan_cm(self, app: FastAPI):
        await self.connect()
        try:
            yield
        finally:
            await self.disconnect()

    def lifespan(self, app: FastAPI):
        return self._lifespan_cm(app)


# ── Shared singleton ──────────────────────────────────────────────────────────
db = DatabasePool()


def get_db():
    """FastAPI dependency — yields a psycopg2 connection, closes after request."""
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()
