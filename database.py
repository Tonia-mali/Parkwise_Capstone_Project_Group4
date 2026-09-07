# database.py — ParkWise Nairobi
# DatabasePool class using pg8000 — pure Python, works on Python 3.14.

import os
import pg8000.native
from contextlib import asynccontextmanager
from fastapi import FastAPI
from urllib.parse import urlparse


class DatabasePool:
    """Manages pg8000 connections for the ParkWise FastAPI backend."""

    def __init__(self):
        self._params = self._resolve_params()

    @staticmethod
    def _resolve_params() -> dict:
        """Parse DATABASE_URL into pg8000 connection params."""
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            return {}
        parsed = urlparse(url)
        return {
            "host":     parsed.hostname,
            "port":     parsed.port or 5432,
            "database": parsed.path.lstrip("/"),
            "user":     parsed.username,
            "password": parsed.password,
            "ssl_context": True,
        }

    async def connect(self) -> None:
        if not self._params:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        print("[database] pg8000 ready.")

    async def disconnect(self) -> None:
        print("[database] Shutdown complete.")

    def get_connection(self):
        """Open and return a new pg8000 connection."""
        if not self._params:
            raise RuntimeError("DATABASE_URL is not set.")
        return pg8000.native.Connection(**self._params)

    @asynccontextmanager
    async def _lifespan_cm(self, app: FastAPI):
        await self.connect()
        try:
            yield
        finally:
            await self.disconnect()

    def lifespan(self, app: FastAPI):
        return self._lifespan_cm(app)


# Shared singleton
db = DatabasePool()


def get_db():
    """FastAPI dependency — yields a pg8000 connection, closes after request."""
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()
