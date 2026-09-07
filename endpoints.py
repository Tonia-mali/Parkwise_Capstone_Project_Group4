# endpoints.py — ParkWise Nairobi
# One class per resource. Switched to psycopg2 for Python 3.14 compatibility.
#
# In main.py:
#   from endpoints import build_router
#   app.include_router(build_router())

from typing import Optional
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db


# ── Pydantic models ───────────────────────────────────────────────────────────

class DemandPredictionIn(BaseModel):
    osm_id: int
    hour_of_day: int
    day_of_week: int
    pressure_score: float
    demand_level: Optional[str] = None


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
    def __init__(self):
        self.router = APIRouter()
        self.register()

    def register(self):
        raise NotImplementedError


# ── Facilities ────────────────────────────────────────────────────────────────

class FacilityRoutes(BaseRoutes):

    def register(self):

        @self.router.get("/facilities")
        def list_facilities(conn=Depends(get_db)):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM facilities ORDER BY osm_id")
                return cur.fetchall()

        @self.router.get("/facilities/{osm_id}")
        def get_facility(osm_id: int, conn=Depends(get_db)):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM facilities WHERE osm_id = %s", (osm_id,))
                row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Facility not found")
            return row


# ── Demand Predictions ────────────────────────────────────────────────────────

class PredictionRoutes(BaseRoutes):

    def register(self):

        @self.router.post("/demand-predictions", status_code=201)
        def create_prediction(payload: DemandPredictionIn, conn=Depends(get_db)):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO demand_predictions
                        (osm_id, hour_of_day, day_of_week, pressure_score, demand_level)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (payload.osm_id, payload.hour_of_day, payload.day_of_week,
                     payload.pressure_score, payload.demand_level),
                )
            conn.commit()
            return {"status": "ok"}

        @self.router.get("/demand-predictions/{osm_id}")
        def get_predictions(osm_id: int, conn=Depends(get_db)):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM demand_predictions
                    WHERE osm_id = %s
                    ORDER BY predicted_at DESC
                    LIMIT 24
                    """,
                    (osm_id,),
                )
                return cur.fetchall()


# ── CNN Counts (stub) ─────────────────────────────────────────────────────────

class CNNRoutes(BaseRoutes):

    def register(self):

        @self.router.post("/cnn-counts", status_code=501)
        def create_cnn_count(payload: CNNCountIn):
            return {"status": "not implemented", "detail": "CNN integration pending Person 3's model."}

        @self.router.get("/cnn-counts/{osm_id}", status_code=501)
        def get_cnn_counts(osm_id: int):
            return {"status": "not implemented", "detail": "CNN integration pending Person 3's model."}


# ── Users ─────────────────────────────────────────────────────────────────────

class UserRoutes(BaseRoutes):

    def register(self):

        @self.router.post("/users", status_code=201)
        def create_user(payload: UserCreate, conn=Depends(get_db)):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, is_guest)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, is_guest, created_at
                    """,
                    (payload.email, payload.password_hash, payload.is_guest),
                )
                row = cur.fetchone()
            conn.commit()
            return row

        @self.router.get("/users/{user_id}")
        def get_user(user_id: int, conn=Depends(get_db)):
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, email, is_guest, created_at, last_seen_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            return row

        @self.router.patch("/users/{user_id}/last-seen")
        def update_last_seen(user_id: int, conn=Depends(get_db)):
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_seen_at = NOW() WHERE id = %s", (user_id,))
            conn.commit()
            return {"status": "ok"}


# ── Router factory ────────────────────────────────────────────────────────────

def build_router() -> APIRouter:
    combined = APIRouter()
    for route_class in [FacilityRoutes, PredictionRoutes, CNNRoutes, UserRoutes]:
        instance = route_class()
        combined.include_router(instance.router)
    return combined
