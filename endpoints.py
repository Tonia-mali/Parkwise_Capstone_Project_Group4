# endpoints.py — ParkWise Nairobi
# One class per resource. Uses pg8000 pure Python driver.

from typing import Optional
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


def rows_to_dicts(columns, rows):
    """Convert pg8000 rows (list of tuples) to list of dicts."""
    return [dict(zip(columns, row)) for row in rows]


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
            result = conn.run("SELECT * FROM facilities ORDER BY osm_id")
            cols = [c["name"] for c in conn.columns]
            return rows_to_dicts(cols, result)

        @self.router.get("/facilities/{osm_id}")
        def get_facility(osm_id: int, conn=Depends(get_db)):
            result = conn.run(
                "SELECT * FROM facilities WHERE osm_id = :osm_id",
                osm_id=osm_id
            )
            if not result:
                raise HTTPException(status_code=404, detail="Facility not found")
            cols = [c["name"] for c in conn.columns]
            return rows_to_dicts(cols, result)[0]


# ── Demand Predictions ────────────────────────────────────────────────────────

class PredictionRoutes(BaseRoutes):

    def register(self):

        @self.router.post("/demand-predictions", status_code=201)
        def create_prediction(payload: DemandPredictionIn, conn=Depends(get_db)):
            conn.run(
                """INSERT INTO demand_predictions
                   (osm_id, hour_of_day, day_of_week, pressure_score, demand_level)
                   VALUES (:osm_id, :hour, :dow, :pressure, :level)""",
                osm_id=payload.osm_id,
                hour=payload.hour_of_day,
                dow=payload.day_of_week,
                pressure=payload.pressure_score,
                level=payload.demand_level,
            )
            return {"status": "ok"}

        @self.router.get("/demand-predictions/{osm_id}")
        def get_predictions(osm_id: int, conn=Depends(get_db)):
            result = conn.run(
                """SELECT * FROM demand_predictions
                   WHERE osm_id = :osm_id
                   ORDER BY predicted_at DESC LIMIT 24""",
                osm_id=osm_id,
            )
            cols = [c["name"] for c in conn.columns]
            return rows_to_dicts(cols, result)


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
            result = conn.run(
                """INSERT INTO users (email, password_hash, is_guest)
                   VALUES (:email, :pwd, :guest)
                   RETURNING id, email, is_guest, created_at""",
                email=payload.email,
                pwd=payload.password_hash,
                guest=payload.is_guest,
            )
            cols = [c["name"] for c in conn.columns]
            return rows_to_dicts(cols, result)[0]

        @self.router.get("/users/{user_id}")
        def get_user(user_id: int, conn=Depends(get_db)):
            result = conn.run(
                """SELECT id, email, is_guest, created_at, last_seen_at
                   FROM users WHERE id = :uid""",
                uid=user_id,
            )
            if not result:
                raise HTTPException(status_code=404, detail="User not found")
            cols = [c["name"] for c in conn.columns]
            return rows_to_dicts(cols, result)[0]

        @self.router.patch("/users/{user_id}/last-seen")
        def update_last_seen(user_id: int, conn=Depends(get_db)):
            conn.run("UPDATE users SET last_seen_at = NOW() WHERE id = :uid", uid=user_id)
            return {"status": "ok"}


# ── Router factory ────────────────────────────────────────────────────────────

def build_router() -> APIRouter:
    combined = APIRouter()
    for route_class in [FacilityRoutes, PredictionRoutes, CNNRoutes, UserRoutes]:
        instance = route_class()
        combined.include_router(instance.router)
    return combined
