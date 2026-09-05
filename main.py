"""
ParkWise Nairobi — FastAPI Backend (no-pandas version)
Reads CSVs with the standard library csv module.
Works on any Python version including 3.14.
"""

import csv
import math
import os
import json
import joblib
import time
import io
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import holidays
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
        "https://parkwise-capstone-project-group4.onrender.com",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "*",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# 2. PATHS + CONSTANTS
# ─────────────────────────────────────────────

BASE_DIR      = Path(__file__).parent
MASTER_CSV    = BASE_DIR / "data" / "nairobi_parking_master_dataset.csv"
OBS_CSV       = BASE_DIR / "data" / "nairobi_parking_expanded_observations.csv"
MODEL_PATH    = BASE_DIR / "data" / "parkwise_model2_gbr.joblib"
FEATURES_PATH = BASE_DIR / "data" / "model2_feature_list.json"
CNN_PATH      = BASE_DIR / "data" / "resnet18_parkwise.pt"

GMAPS_KEY          = "AIzaSyANqZ_js02DE14k69HBAxmVTmatLSel-As"
CNN_CACHE_SECONDS  = 1800   # 30 minutes per facility
CNN_TIMEOUT_SEC    = 10     # satellite image fetch + inference timeout

# ─────────────────────────────────────────────
# 3. IN-MEMORY DATA STORE
# ─────────────────────────────────────────────

facilities: dict   = {}     # osm_id (int) -> row dict
hourly_curves: dict = {}    # {0: {hour: float}, 1: {hour: float}}
ml_model           = None
ml_features: list  = []
cnn_model          = None   # ResNet-18 regression model
cnn_cache: dict    = {}     # facility_id -> {"ts": float, "result": dict}
KE_HOLIDAYS        = holidays.Kenya()


def safe_float(val, default=0.0):
    try:
        return float(val) if val not in (None, "", "nan") else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    try:
        return int(float(val)) if val not in (None, "", "nan") else default
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────
# 4. STARTUP — load all models + data
# ─────────────────────────────────────────────

@app.on_event("startup")
def load_data():
    global facilities, hourly_curves, ml_model, ml_features, cnn_model

    # ── Master dataset ──────────────────────────────────────────────────
    if not MASTER_CSV.exists():
        raise RuntimeError(f"Master CSV not found: {MASTER_CSV}")

    with open(MASTER_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            osm_id = safe_int(row.get("osm_id", 0))
            if osm_id == 0:
                continue

            zone = row.get("zone", "")
            if not zone:
                tariff = row.get("tariff_model", "")
                zone = "Zone I" if "Zone I" in tariff else "Zone II"

            cat  = row.get("category", "")
            tier = "tier1_cbd" if ("On-Street" in cat and zone == "Zone I") else "tier2_other"

            facilities[osm_id] = {
                "osm_id": osm_id,
                "facility_name_clean": row.get("facility_name_clean", row.get("facility_name", "")),
                "latitude": safe_float(row.get("latitude")),
                "longitude": safe_float(row.get("longitude")),
                "base_rate_kes": safe_float(row.get("base_rate_kes", 100), 100),
                "parking_pressure_score": safe_float(row.get("parking_pressure_score", 75), 75),
                "traffic_delay_index": safe_float(row.get("traffic_delay_index", 1.0), 1.0),
                "security_score": safe_float(row.get("security_score", 3.5), 3.5),
                "overall_rating": safe_float(row.get("overall_rating")) or None,
                "operating_hours": row.get("operating_hours", "24/7"),
                "operating_schedule": row.get("operating_schedule", ""),
                "category": cat,
                "zone": zone,
                "tier": tier,
                "payment_channels": row.get("payment_channels", "M-Pesa, Cash"),
                "penalty_fee_kes": safe_float(row.get("penalty_fee_kes", 500), 500),
                "calibration_status": row.get("calibration_status", "estimated"),
                "estimated_capacity": safe_float(row.get("total_capacity_bays")) or None,
            }

    print(f"[startup] Loaded {len(facilities)} facilities")

    # ── Hourly curves ───────────────────────────────────────────────────
    if OBS_CSV.exists():
        sums   = {0: {}, 1: {}}
        counts = {0: {}, 1: {}}

        with open(OBS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                is_wknd = safe_int(row.get("is_weekend", 0))
                hour    = safe_int(row.get("hour_of_day", 0))
                rate    = safe_float(row.get("occupancy_rate", 0.0))
                sums[is_wknd][hour]   = sums[is_wknd].get(hour, 0.0) + rate
                counts[is_wknd][hour] = counts[is_wknd].get(hour, 0) + 1

        for wknd in [0, 1]:
            avg  = {h: sums[wknd][h] / counts[wknd][h] for h in sums[wknd]}
            peak = max(avg.values()) if avg else 1.0
            hourly_curves[wknd] = {h: round(v / peak, 4) for h, v in avg.items()}

        print(f"[startup] Hourly curves built — weekday hours: {sorted(hourly_curves.get(0, {}).keys())}")
    else:
        _wd = {6:0.463,7:0.468,8:0.990,9:0.978,10:0.985,11:0.989,12:0.816,
               13:0.997,14:0.994,15:1.000,16:0.993,17:0.810,18:0.821,
               19:0.475,20:0.464,21:0.461,22:0.463}
        hourly_curves[0] = _wd
        hourly_curves[1] = _wd
        print("[startup] OBS csv not found — using built-in curve fallback")

    # ── GBR ML model ────────────────────────────────────────────────────
    if MODEL_PATH.exists():
        try:
            ml_model = joblib.load(MODEL_PATH)
            if FEATURES_PATH.exists():
                with open(FEATURES_PATH) as fp:
                    ml_features = json.load(fp).get("features", [])
            print("[startup] GBR ML model loaded")
        except Exception as e:
            print(f"[startup] GBR model load failed ({e}) — using curve fallback")
            ml_model = None
    else:
        print("[startup] No GBR model — using curve fallback")

    # ── CNN ResNet-18 model ─────────────────────────────────────────────
    if CNN_PATH.exists():
        try:
            import torch
            import torch.nn as nn
            from torchvision import models as tv_models

            m = tv_models.resnet18(weights=None)
            m.fc = nn.Linear(512, 1)
            state = torch.load(str(CNN_PATH), map_location="cpu", weights_only=False)
            m.load_state_dict(state, strict=False)
            m.eval()
            cnn_model = m
            print("[startup] CNN ResNet-18 model loaded")
        except Exception as e:
            print(f"[startup] CNN model load failed ({e}) — occupancy/detect will use pressure fallback")
            cnn_model = None
    else:
        print("[startup] CNN model file not found — occupancy/detect will use pressure fallback")


# ─────────────────────────────────────────────
# 5. HELPERS
# ─────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def pressure_to_status(pressure: float) -> str:
    if pressure >= 90: return "full"
    if pressure >= 75: return "limited"
    return "available"


def occupancy_to_status(fraction: float) -> str:
    if fraction >= 0.9: return "full"
    if fraction >= 0.5: return "limited"
    return "available"


def get_curve(is_weekend: int) -> dict:
    return hourly_curves.get(is_weekend, hourly_curves.get(0, {}))


def predict_pressure_curve(fac: dict, is_weekend: int) -> dict:
    base  = fac["parking_pressure_score"]
    curve = get_curve(is_weekend)
    results = {}

    if ml_model is not None and ml_features:
        try:
            import numpy as np
            now      = datetime.now(timezone.utc)
            dow      = now.weekday()
            base_rate = float(fac.get("base_rate_kes", 100))
            prev_occ  = base / 100.0
            rows = []
            for h in range(6, 23):
                h_sin = math.sin(2 * math.pi * h / 24)
                h_cos = math.cos(2 * math.pi * h / 24)
                d_sin = math.sin(2 * math.pi * dow / 7)
                d_cos = math.cos(2 * math.pi * dow / 7)
                row_dict = {
                    "facility_name": fac.get("facility_name_clean", "Unknown"),
                    "hour_sin": h_sin, "hour_cos": h_cos,
                    "day_sin": d_sin,  "day_cos": d_cos,
                    "is_weekend": float(is_weekend),
                    "is_peak_hour": float(h in [7, 8, 9, 16, 17, 18]),
                    "previous_occupancy": prev_occ,
                    "occupancy_rolling_3": prev_occ,
                    "base_rate_kes": base_rate,
                }
                rows.append([row_dict.get(k, 0) for k in ml_features])
            preds = ml_model.predict(rows)
            for i, h in enumerate(range(6, 23)):
                results[h] = round(float(min(100.0, max(0.0, preds[i]))), 1)
            return results
        except Exception as e:
            print(f"[predict] ML prediction failed: {e} — using curve fallback")

    for h in range(6, 23):
        scale = curve.get(h, 0.75)
        pred  = min(100.0, max(20.0, base * scale))
        results[h] = round(pred, 1)
    return results


def find_by_coords(lat: float, lon: float, tolerance_km: float = 0.05):
    best_id, best_dist = None, float("inf")
    for osm_id, fac in facilities.items():
        d = haversine_km(lat, lon, fac["latitude"], fac["longitude"])
        if d < best_dist:
            best_dist = d
            best_id   = osm_id
    if best_id and best_dist <= tolerance_km:
        return facilities[best_id]
    return None


def _reason(pressure, dist_km, price, walk_min):
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


def run_cnn_inference(lat: float, lon: float, capacity: int) -> dict:
    """Download satellite image, run ResNet-18, return occupancy dict."""
    import torch
    from PIL import Image
    import torchvision.transforms as T

    url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lon}&zoom=19&size=400x400"
        f"&maptype=satellite&key={GMAPS_KEY}"
    )
    req  = urllib.request.urlopen(url, timeout=CNN_TIMEOUT_SEC)
    img  = Image.open(io.BytesIO(req.read())).convert("RGB")

    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    tensor = transform(img).unsqueeze(0)

    with torch.no_grad():
        raw = float(cnn_model(tensor).item())

    car_count    = max(0, min(capacity, round(raw)))
    empty_spaces = capacity - car_count
    occ_frac     = car_count / capacity if capacity > 0 else 0.0
    occ_pct      = round(occ_frac * 100, 1)

    return {
        "car_count":          car_count,
        "empty_spaces":       empty_spaces,
        "capacity":           capacity,
        "occupancy_fraction": round(occ_frac, 4),
        "occupancy_percent":  occ_pct,
        "status":             occupancy_to_status(occ_frac),
        "source":             "resnet18_live",
        "cached":             False,
    }


def pressure_fallback(fac: dict, capacity: int) -> dict:
    """Return occupancy estimate from pressure score when CNN unavailable."""
    pressure  = fac["parking_pressure_score"]
    occ_frac  = round(min(1.0, pressure / 100.0), 4)
    car_count = max(0, min(capacity, round(occ_frac * capacity)))
    empty     = capacity - car_count
    occ_pct   = round(occ_frac * 100, 1)
    return {
        "car_count":          car_count,
        "empty_spaces":       empty,
        "capacity":           capacity,
        "occupancy_fraction": occ_frac,
        "occupancy_percent":  occ_pct,
        "status":             occupancy_to_status(occ_frac),
        "source":             "pressure_fallback",
        "cached":             False,
    }


# ─────────────────────────────────────────────
# 6. ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service":           "ParkWise Nairobi API",
        "version":           "1.0.0",
        "facilities_loaded": len(facilities),
        "model_loaded":      ml_model is not None,
        "cnn_loaded":        cnn_model is not None,
        "endpoints": [
            "/predict/demand",
            "/recommend",
            "/availability/snapshot",
            "/occupancy/detect",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {
        "status":           "ok",
        "facilities":       len(facilities),
        "model":            "loaded" if ml_model is not None else "curve_fallback",
        "cnn":              "loaded" if cnn_model is not None else "not_loaded",
        "sklearn_required": "1.9.0",
    }


@app.get("/predict/demand")
def predict_demand(
    lat:         float        = Query(...),
    lon:         float        = Query(...),
    facility_id: Optional[int] = Query(None),
):
    fac = None
    if facility_id is not None:
        fac = facilities.get(facility_id)
    if fac is None:
        fac = find_by_coords(lat, lon)
    if fac is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    now        = datetime.now(timezone.utc)
    is_weekend = int(now.weekday() >= 5)
    cur_hour   = now.hour
    curve      = predict_pressure_curve(fac, is_weekend)

    chart_hours = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    predictions = [{"hour": h, "pressure": curve.get(h, curve.get(h-1, 75.0))} for h in chart_hours]
    current_pressure = curve.get(cur_hour, fac["parking_pressure_score"])

    return {
        "facility_id":      fac["osm_id"],
        "facility_name":    fac["facility_name_clean"],
        "predictions":      predictions,
        "current_pressure": round(current_pressure, 1),
        "status":           pressure_to_status(current_pressure),
        "base_pressure":    round(fac["parking_pressure_score"], 1),
    }


@app.get("/recommend")
def recommend(
    user_lat:       float        = Query(...),
    user_lon:       float        = Query(...),
    time:           Optional[int] = Query(None),
    day_of_week:    Optional[int] = Query(None),
    top_n:          int           = Query(5, ge=1, le=20),
    max_distance_km: float        = Query(2.0),
):
    if not facilities:
        raise HTTPException(status_code=503, detail="Data not loaded")

    now        = datetime.now(timezone.utc)
    hour       = time        if time        is not None else now.hour
    dow        = day_of_week if day_of_week is not None else now.weekday()
    is_weekend = int(dow >= 5)

    rows = []
    for osm_id, fac in facilities.items():
        dist = haversine_km(user_lat, user_lon, fac["latitude"], fac["longitude"])
        if dist <= max_distance_km:
            rows.append((osm_id, fac, dist))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No facilities within {max_distance_km}km")

    max_dist  = max(r[2] for r in rows)
    prices    = [r[1]["base_rate_kes"] for r in rows]
    min_price, max_price = min(prices), max(prices)
    price_rng = (max_price - min_price) or 1.0

    scored = []
    for osm_id, fac, dist in rows:
        curve         = predict_pressure_curve(fac, is_weekend)
        hour_pressure = curve.get(hour, fac["parking_pressure_score"])
        if pressure_to_status(hour_pressure) == "full":
            continue

        price    = fac["base_rate_kes"]
        nd       = dist / max_dist
        np_      = (price - min_price) / price_rng
        npress   = hour_pressure / 100.0
        score    = round((1 - nd)*0.50 + (1 - npress)*0.30 + (1 - np_)*0.20, 4)
        walk_min = round((dist / 5) * 60)

        scored.append({
            "facility_id":        osm_id,
            "name":               fac["facility_name_clean"],
            "display_name":       fac["facility_name_clean"],
            "latitude":           round(fac["latitude"], 7),
            "longitude":          round(fac["longitude"], 7),
            "score":              score,
            "predicted_pressure": round(hour_pressure, 1),
            "status":             pressure_to_status(hour_pressure),
            "distance_km":        round(dist, 3),
            "walk_minutes":       walk_min,
            "base_rate_kes":      price,
            "zone":               fac["zone"],
            "reason":             _reason(hour_pressure, dist, price, walk_min),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "user_lat":         user_lat,
        "user_lon":         user_lon,
        "hour":             hour,
        "day_of_week":      dow,
        "recommendations":  scored[:top_n],
        "total_candidates": len(scored),
    }


@app.get("/availability/snapshot")
def availability_snapshot():
    if not facilities:
        raise HTTPException(status_code=503, detail="Data not loaded")

    now            = datetime.now(timezone.utc)
    is_weekend     = int(now.weekday() >= 5)
    cur_hour       = now.hour
    curve_template = get_curve(is_weekend)

    fac_list               = []
    available = limited = full = 0

    for osm_id, fac in facilities.items():
        base_p = fac["parking_pressure_score"]
        scale  = curve_template.get(cur_hour, 0.75)
        cur_p  = round(min(100.0, max(20.0, base_p * scale)), 1)
        status = pressure_to_status(cur_p)

        if status == "available": available += 1
        elif status == "limited": limited   += 1
        else:                     full      += 1

        fac_list.append({"facility_id": osm_id, "status": status, "pressure": cur_p})

    avg_base    = sum(f["parking_pressure_score"] for f in facilities.values()) / len(facilities)
    hourly_chart = []
    for h in range(6, 23):
        scale        = curve_template.get(h, 0.75)
        city_pressure = round(min(100.0, max(20.0, avg_base * scale)), 1)
        hourly_chart.append({"hour": h, "pressure": city_pressure})

    return {
        "timestamp":    now.isoformat(),
        "total":        len(fac_list),
        "available":    available,
        "limited":      limited,
        "full":         full,
        "hourly_chart": hourly_chart,
        "facilities":   fac_list,
    }


@app.get("/occupancy/detect")
def occupancy_detect(
    lat:         float        = Query(..., description="Facility latitude"),
    lon:         float        = Query(..., description="Facility longitude"),
    facility_id: Optional[int] = Query(None, description="OSM facility ID"),
    capacity:    int           = Query(20,  description="Total parking bays", ge=1, le=500),
):
    """
    Fetch a live Google satellite image of the parking facility,
    run ResNet-18 inference to count cars, and return occupancy.
    Results are cached 30 minutes per facility.
    Falls back to pressure score if CNN is unavailable.
    """

    # Resolve facility for fallback pressure score
    fac = None
    if facility_id is not None:
        fac = facilities.get(facility_id)
    if fac is None:
        fac = find_by_coords(lat, lon)

    cache_key = str(facility_id) if facility_id else f"{lat:.5f},{lon:.5f}"

    # ── Check cache ─────────────────────────────────────────────────────
    cached = cnn_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < CNN_CACHE_SECONDS:
        result = dict(cached["result"])
        result["cached"] = True
        return {
            "osm_id":   facility_id,
            "facility": fac["facility_name_clean"] if fac else None,
            **result,
        }

    # ── CNN inference ────────────────────────────────────────────────────
    if cnn_model is not None:
        try:
            result = run_cnn_inference(lat, lon, capacity)
            cnn_cache[cache_key] = {"ts": time.time(), "result": result}
            return {
                "osm_id":   facility_id,
                "facility": fac["facility_name_clean"] if fac else None,
                **result,
            }
        except Exception as e:
            print(f"[occupancy/detect] CNN inference failed: {e} — using pressure fallback")

    # ── Pressure fallback ────────────────────────────────────────────────
    if fac is None:
        raise HTTPException(status_code=404, detail="Facility not found and CNN unavailable")

    result = pressure_fallback(fac, capacity)
    return {
        "osm_id":   facility_id,
        "facility": fac["facility_name_clean"],
        **result,
    }
