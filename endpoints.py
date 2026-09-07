# endpoints.py — ParkWise Nairobi
# One class per resource. Each class owns its routes and registers them
# onto a shared APIRouter via its register() method.
#
# In main.py:
#   from endpoints import build_router
#   app.include_router(build_router())

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_pool


# ── Pydantic models ───────────────────────────────────────────────────────────

class DemandPredictionIn(BaseModel):
    osm_id: int
    hour_of_day: int
    day_of_week: int
    pressure_score: float
    demand_level: Optional[str] = None   # 'low' | 'medium' | 'high'


class CNNCountIn(BaseModel):
    osm_id: int
    car_count: int
    image_source: Optional[str] = None


class UserCreate(BaseModel):
    email: Optional[str] = None
    password_hash: Optional[str] = None
    is_guest: bool = False


# ── Base class ────────────────────────────────────────────────────────────────

class BaseRoutes:
    """
    Base class for all route groups.
    Subclasses call self.router in register() to attach their routes.
    """

    def __init__(self):
        self.router = APIRouter()
        self.register()

    def register(self):
        """Override in each subclass to attach routes to self.router."""
        raise NotImplementedError


# ── Facilities ────────────────────────────────────────────────────────────────

class FacilityRoutes(BaseRoutes):
    """GET /facilities and GET /facilities/{osm_id}"""

    def register(self):

        @self.router.get("/facilities")
        async def list_facilities(db: asyncpg.Pool = Depends(get_pool)):
            """Return all 500 parking facilities."""
            rows = await db.fetch("SELECT * FROM facilities ORDER BY osm_id")
            return [dict(r) for r in rows]

        @self.router.get("/facilities/{osm_id}")
        async def get_facility(osm_id: int, db: asyncpg.Pool = Depends(get_pool)):
            """Return a single facility by OSM ID."""
            row = await db.fetchrow(
                "SELECT * FROM facilities WHERE osm_id = $1", osm_id
            )
            if not row:
                raise HTTPException(status_code=404, detail="Facility not found")
            return dict(row)


# ── Demand Predictions ────────────────────────────────────────────────────────

class PredictionRoutes(BaseRoutes):
    """POST /demand-predictions and GET /demand-predictions/{osm_id}"""

    def register(self):

        @self.router.post("/demand-predictions", status_code=201)
        async def create_prediction(
            payload: DemandPredictionIn,
            db: asyncpg.Pool = Depends(get_pool),
        ):
            """Save a new HistGradientBoosting prediction for a facility."""
            await db.execute(
                """
                INSERT INTO demand_predictions
                    (osm_id, hour_of_day, day_of_week, pressure_score, demand_level)
                VALUES ($1, $2, $3, $4, $5)
                """,
                payload.osm_id,
                payload.hour_of_day,
                payload.day_of_week,
                payload.pressure_score,
                payload.demand_level,
            )
            return {"status": "ok"}

        @self.router.get("/demand-predictions/{osm_id}")
        async def get_predictions(
            osm_id: int,
            db: asyncpg.Pool = Depends(get_pool),
        ):
            """Return the 24 most recent predictions for a facility."""
            rows = await db.fetch(
                """
                SELECT * FROM demand_predictions
                WHERE osm_id = $1
                ORDER BY predicted_at DESC
                LIMIT 24
                """,
                osm_id,
            )
            return [dict(r) for r in rows]


# ── CNN Counts (stub) ─────────────────────────────────────────────────────────

class CNNRoutes(BaseRoutes):
    """Stubs for /cnn-counts — pending Person 3's ResNet-18 model."""

    def register(self):

        @self.router.post("/cnn-counts", status_code=501)
        async def create_cnn_count(payload: CNNCountIn):
            return {
                "status": "not implemented",
                "detail": "CNN integration pending Person 3's model.",
            }

        @self.router.get("/cnn-counts/{osm_id}", status_code=501)
        async def get_cnn_counts(osm_id: int):
            return {
                "status": "not implemented",
                "detail": "CNN integration pending Person 3's model.",
            }


# ── Users ─────────────────────────────────────────────────────────────────────

class UserRoutes(BaseRoutes):
    """POST /users, GET /users/{id}, PATCH /users/{id}/last-seen"""

    def register(self):

        @self.router.post("/users", status_code=201)
        async def create_user(
            payload: UserCreate,
            db: asyncpg.Pool = Depends(get_pool),
        ):
            """Create a new user or guest session."""
            row = await db.fetchrow(
                """
                INSERT INTO users (email, password_hash, is_guest)
                VALUES ($1, $2, $3)
                RETURNING id, email, is_guest, created_at
                """,
                payload.email,
                payload.password_hash,
                payload.is_guest,
            )
            return dict(row)

        @self.router.get("/users/{user_id}")
        async def get_user(user_id: int, db: asyncpg.Pool = Depends(get_pool)):
            """Return a user by ID."""
            row = await db.fetchrow(
                """
                SELECT id, email, is_guest, created_at, last_seen_at
                FROM users WHERE id = $1
                """,
                user_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            return dict(row)

        @self.router.patch("/users/{user_id}/last-seen")
        async def update_last_seen(
            user_id: int,
            db: asyncpg.Pool = Depends(get_pool),
        ):
            """Update last_seen_at timestamp for a user."""
            await db.execute(
                "UPDATE users SET last_seen_at = NOW() WHERE id = $1", user_id
            )
            return {"status": "ok"}


# ── Router factory ────────────────────────────────────────────────────────────

def build_router() -> APIRouter:
    """
    Instantiate all route classes and merge their routers into one.
    Import and call this in main.py:

        from endpoints import build_router
        app.include_router(build_router())
    """
    combined = APIRouter()
    for route_class in [FacilityRoutes, PredictionRoutes, CNNRoutes, UserRoutes]:
        instance = route_class()
        combined.include_router(instance.router)
    return combined
