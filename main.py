"""
ParkWise Nairobi — FastAPI Backend
Person 5 implementation

Data sources (no live model required at startup):
  - nairobi_parking_master_dataset.csv  →  500 facilities, pressure scores, all metadata
  - nairobi_parking_expanded_observations.csv  →  hourly demand curves (weekday / weekend)

If parkwise_model2_gbr.joblib exists it is loaded and used for /predict/demand.
If it is absent the server falls back to the curve × pressure score approach,
which is already calibrated and perfectly suitable for the capstone demo.
"""

import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import holidays
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────
# 1. APP + CORS
# ─────────────────────────────────────────────

app = FastAPI(
    title="ParkWise Nairobi API",
    description="Parking demand prediction and smart recommendation for Nairobi CBD",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.vercel.app",
        "https://parkwise-v3-bbam.vercel.app",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# 2. PATHS  (relative to this file so Railway finds them)
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
MASTER_CSV   = BASE_DIR / "data" / "nairobi_parking_master_dataset.csv"
OBS_CSV      = BASE_DIR / "data" / "nairobi_parking_expanded_observations.csv"
MODEL_PATH   = BASE_DIR / "data" / "parkwise_model2_gbr.joblib"
FEATURES_PATH= BASE_DIR / "data" / "model2_feature_list.json"

# ─────────────────────────────────────────────
# 3. STARTUP — load data once into memory
# ─────────────────────────────────────────────

master_df: pd.DataFrame = pd.DataFrame()
hourly_curves: dict = {}   # {0: {h: norm_val}, 1: {h: norm_val}}  0=weekday 1=weekend
ml_model = None
ml_features: list = []
KE_HOLIDAYS = holidays.Kenya()


@app.on_event("startup")
def load_data():
    global master_df, hourly_curves, ml_model, ml_features

    # ── Master dataset ──────────────────────────────────────────────────
    if not MASTER_CSV.exists():
        raise RuntimeError(f"Master dataset not found at {MASTER_CSV}")

    master_df = pd.read_csv(MASTER_CSV)

    # Derived: zone from tariff_model if column absent
    if "zone" not in master_df.columns:
        master_df["zone"] = master_df["tariff_model"].apply(
            lambda t: "Zone I" if isinstance(t, str) and "Zone I" in t else "Zone II"
        )

    # Derived: tier
    if "tier" not in master_df.columns:
        master_df["tier"] = master_df.apply(
            lambda r: "tier1_cbd"
            if "On-Street" in str(r["category"]) and r.get("zone") == "Zone I"
            else "tier2_other",
            axis=1,
        )

    # Index by osm_id for fast lookup
    master_df["osm_id"] = master_df["osm_id"].astype(int)
    master_df = master_df.set_index("osm_id")

    print(f"[startup] Loaded {len(master_df)} facilities from master dataset")

    # ── Hourly curves ───────────────────────────────────────────────────
    if OBS_CSV.exists():
        obs = pd.read_csv(OBS_CSV)
        for is_wknd in [0, 1]:
            grp = obs[obs["is_weekend"] == is_wknd]
            curve = grp.groupby("hour_of_day")["occupancy_rate"].mean()
            peak = curve.max()
            hourly_curves[is_wknd] = {int(h): round(float(v / peak), 4) for h, v in curve.items()}
        print(f"[startup] Hourly curves built — weekday hours: {sorted(hourly_curves[0].keys())}")
    else:
        # Hardcoded fallback derived from the observed data above
        _wd = {6:0.463,7:0.468,8:0.990,9:0.978,10:0.985,11:0.989,12:0.816,
               13:0.997,14:0.994,15:1.000,16:0.993,17:0.810,18:0.821,
               19:0.475,20:0.464,21:0.461,22:0.463}
        hourly_curves[0] = _wd
        hourly_curves[1] = _wd   # weekend same shape as fallback
        print("[startup] OBS csv not found — using built-in curve fallback")

    # ── Optional ML model ───────────────────────────────────────────────
    if MODEL_PATH.exists():
        try:
            ml_model = joblib.load(MODEL_PATH)
            if FEATURES_PATH.exists():
                import json
                with open(FEATURES_PATH) as fp:
                    ml_features = json.load(fp).get("features", [])
            print(f"[startup] ML model loaded — features: {ml_features}")
        except Exception as e:
            print(f"[startup] ML model load failed ({e}) — using curve fallback")
            ml_model = None
    else:
        print("[startup] No ML model file found — using curve fallback (expected for demo)")


# ─────────────────────────────────────────────
# 4. HELPERS
# ─────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def pressure_to_status(pressure: float) -> str:
    """Convert 0-100 pressure score to status string."""
    if pressure >= 90:
        return "full"
    if pressure >= 75:
        return "limited"
    return "available"


def get_curve(is_weekend: int) -> dict:
    return hourly_curves.get(is_weekend, hourly_curves.get(0, {}))


def predict_pressure_curve(fac_row: pd.Series, is_weekend: int) -> dict[int, float]:
    """
    Returns {hour: pressure_0_to_100} for hours 6-22.

    Strategy:
      1. If ML model loaded and features available → use model for each hour
      2. Otherwise → base_pressure × hourly_curve
    """
    base = float(fac_row["parking_pressure_score"])   # already 0-100, calibrated
    curve = get_curve(is_weekend)

    if ml_model is not None and ml_features:
        now = datetime.now(timezone.utc)
        results = {}
        for h in range(6, 23):
            dow = now.weekday()  # 0=Mon
            is_hol = int(now.date() in KE_HOLIDAYS)
            h_sin = math.sin(2 * math.pi * h / 24)
            h_cos = math.cos(2 * math.pi * h / 24)
            d_sin = math.sin(2 * math.pi * dow / 7)
            d_cos = math.cos(2 * math.pi * dow / 7)

            row_dict = {
                "hour_sin": h_sin,
                "hour_cos": h_cos,
                "day_sin": d_sin,
                "day_cos": d_cos,
                "is_weekend": is_weekend,
                "is_peak_hour": int(h in [7, 8, 9, 16, 17, 18]),
                "is_public_holiday": is_hol,
                "previous_occupancy": base,
                "occupancy_rolling_3": base,
                "traffic_delay_index": float(fac_row.get("traffic_delay_index", 1.0)),
                "base_rate_kes": float(fac_row.get("base_rate_kes", 100)),
            }

            # Only pass features the model was trained on
            X = pd.DataFrame([{k: row_dict.get(k, 0) for k in ml_features}])
            try:
                pred = float(np.clip(ml_model.predict(X)[0], 0, 100))
            except Exception:
                pred = base * curve.get(h, 0.75)
            results[h] = round(pred, 1)
        return results

    # ── Curve fallback ──────────────────────────────────────────────────
    results = {}
    for h in range(6, 23):
        scale = curve.get(h, 0.75)
        # Scale base pressure: at scale=1.0 → base; at scale=0.46 → roughly 46% of base
        # But clamp so we never exceed 100 and never go below a realistic floor (~20)
        pred = min(100.0, max(20.0, base * scale))
        results[h] = round(pred, 1)
    return results


def find_facility_by_coords(lat: float, lon: float, tolerance_km: float = 0.05) -> Optional[pd.Series]:
    """Find nearest facility within tolerance_km. Returns row or None."""
    if master_df.empty:
        return None
    dists = master_df.apply(
        lambda r: haversine_km(lat, lon, float(r["latitude"]), float(r["longitude"])), axis=1
    )
    idx = dists.idxmin()
    if dists[idx] <= tolerance_km:
        return master_df.loc[idx]
    return None


def find_facility_by_id(facility_id: int) -> Optional[pd.Series]:
    if facility_id in master_df.index:
        return master_df.loc[facility_id]
    return None


# ─────────────────────────────────────────────
# 5. ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "ParkWise Nairobi API",
        "version": "1.0.0",
        "facilities_loaded": len(master_df),
        "model_loaded": ml_model is not None,
        "endpoints": ["/predict/demand", "/recommend", "/availability/snapshot", "/health"],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "facilities": len(master_df),
        "model": "loaded" if ml_model is not None else "curve_fallback",
    }


# ── 5a. DEMAND PREDICTION ───────────────────────────────────────────────────

@app.get("/predict/demand")
def predict_demand(
    lat: float = Query(..., description="Facility latitude"),
    lon: float = Query(..., description="Facility longitude"),
    facility_id: Optional[int] = Query(None, description="osm_id (preferred over lat/lon)"),
):
    """
    Returns hourly demand prediction for a single facility.
    Accepts facility_id (osm_id) OR lat/lon.
    """
    # Resolve facility
    fac = None
    if facility_id is not None:
        fac = find_facility_by_id(facility_id)
    if fac is None:
        fac = find_facility_by_coords(lat, lon)
    if fac is None:
        raise HTTPException(status_code=404, detail="Facility not found near provided coordinates")

    now = datetime.now(timezone.utc)
    is_weekend = int(now.weekday() >= 5)
    cur_hour = now.hour

    curve = predict_pressure_curve(fac, is_weekend)

    # Format for the 9-bar chart the frontend draws (hours 6,8,10,12,14,16,18,20,22)
    chart_hours = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    predictions = [
        {"hour": h, "pressure": curve.get(h, curve.get(h - 1, 75.0))}
        for h in chart_hours
    ]

    current_pressure = curve.get(cur_hour, float(fac["parking_pressure_score"]))

    return {
        "facility_id": int(fac.name),
        "facility_name": str(fac.get("facility_name_clean", "")),
        "predictions": predictions,
        "current_pressure": round(current_pressure, 1),
        "status": pressure_to_status(current_pressure),
        "base_pressure": round(float(fac["parking_pressure_score"]), 1),
    }


# ── 5b. SMART PARK RECOMMENDATION ──────────────────────────────────────────

@app.get("/recommend")
def recommend(
    user_lat: float = Query(..., description="User latitude"),
    user_lon: float = Query(..., description="User longitude"),
    time: Optional[int] = Query(None, description="Hour of day 0-23 (defaults to now)"),
    day_of_week: Optional[int] = Query(None, description="0=Mon…6=Sun (defaults to today)"),
    top_n: int = Query(5, ge=1, le=20, description="Number of results to return"),
    max_distance_km: float = Query(2.0, description="Search radius in km"),
):
    """
    Returns ranked parking recommendations for a user location.
    Scoring: 50% distance + 30% pressure (lower = better) + 20% price (lower = better)
    """
    if master_df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    now = datetime.now(timezone.utc)
    hour = time if time is not None else now.hour
    dow  = day_of_week if day_of_week is not None else now.weekday()
    is_weekend = int(dow >= 5)

    # Compute distances and filter to radius
    rows = []
    for osm_id, row in master_df.iterrows():
        dist = haversine_km(user_lat, user_lon, float(row["latitude"]), float(row["longitude"]))
        if dist <= max_distance_km:
            rows.append((osm_id, row, dist))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No facilities within {max_distance_km}km")

    # Score each candidate
    max_dist  = max(r[2] for r in rows)
    prices    = [float(r[1].get("base_rate_kes", 150)) for r in rows]
    min_price = min(prices)
    max_price = max(prices)
    price_rng = (max_price - min_price) or 1.0

    scored = []
    for osm_id, row, dist in rows:
        pressure = float(row["parking_pressure_score"])
        # Get pressure at the requested hour
        curve = predict_pressure_curve(row, is_weekend)
        hour_pressure = curve.get(hour, pressure)

        if pressure_to_status(hour_pressure) == "full":
            continue  # exclude full facilities

        price = float(row.get("base_rate_kes", 150))
        nd = dist / max_dist
        np_ = (price - min_price) / price_rng
        npress = hour_pressure / 100.0

        # Higher score = better: low distance, low pressure, low price
        score = round((1 - nd) * 0.50 + (1 - npress) * 0.30 + (1 - np_) * 0.20, 4)

        walk_min = round((dist / 5) * 60)  # assuming 5 km/h walking

        scored.append({
            "facility_id": int(osm_id),
            "name": str(row.get("facility_name_clean", "")),
            "display_name": str(row.get("facility_name_clean", "")),
            "latitude": round(float(row["latitude"]), 7),
            "longitude": round(float(row["longitude"]), 7),
            "score": score,
            "predicted_pressure": round(hour_pressure, 1),
            "status": pressure_to_status(hour_pressure),
            "distance_km": round(dist, 3),
            "walk_minutes": walk_min,
            "base_rate_kes": price,
            "zone": str(row.get("zone", "Zone I")),
            "reason": _reason(hour_pressure, dist, price, walk_min),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    return {
        "user_lat": user_lat,
        "user_lon": user_lon,
        "hour": hour,
        "day_of_week": dow,
        "recommendations": top,
        "total_candidates": len(scored),
    }


def _reason(pressure: float, dist_km: float, price: float, walk_min: int) -> str:
    parts = []
    if pressure < 75:
        parts.append("Low predicted pressure")
    elif pressure < 85:
        parts.append("Moderate availability")
    if walk_min <= 3:
        parts.append(f"{walk_min} min walk")
    elif walk_min <= 8:
        parts.append(f"{walk_min} min walk")
    if price <= 100:
        parts.append("Budget-friendly")
    elif price >= 300:
        parts.append("Premium facility")
    return ", ".join(parts) if parts else "Good overall option"


# ── 5c. AVAILABILITY SNAPSHOT ───────────────────────────────────────────────

@app.get("/availability/snapshot")
def availability_snapshot():
    """
    Snapshot of all 500 facilities with current status and pressure scores.
    Used for the overview dashboard chart and quick-strip counts.
    """
    if master_df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    now = datetime.now(timezone.utc)
    is_weekend = int(now.weekday() >= 5)
    cur_hour = now.hour
    curve_template = get_curve(is_weekend)

    facilities = []
    available = limited = full = 0

    for osm_id, row in master_df.iterrows():
        base_p = float(row["parking_pressure_score"])
        scale  = curve_template.get(cur_hour, 0.75)
        cur_p  = round(min(100.0, max(20.0, base_p * scale)), 1)
        status = pressure_to_status(cur_p)

        if status == "available":
            available += 1
        elif status == "limited":
            limited += 1
        else:
            full += 1

        facilities.append({
            "facility_id": int(osm_id),
            "status": status,
            "pressure": cur_p,
        })

    # Hourly demand curve for the overview chart (city-wide average)
    avg_base = float(master_df["parking_pressure_score"].mean())
    hourly_chart = []
    for h in range(6, 23):
        scale = curve_template.get(h, 0.75)
        city_pressure = round(min(100.0, max(20.0, avg_base * scale)), 1)
        hourly_chart.append({"hour": h, "pressure": city_pressure})

    return {
        "timestamp": now.isoformat(),
        "total": len(facilities),
        "available": available,
        "limited": limited,
        "full": full,
        "hourly_chart": hourly_chart,   # for the overview chart
        "facilities": facilities,
    }
