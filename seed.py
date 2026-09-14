# seed.py — ParkWise Nairobi
# FacilitySeeder using pg8000 pure Python driver.
#
# Usage:
#   DATABASE_URL=postgresql://... python seed.py

import os
import re
import json
import pg8000.native
from urllib.parse import urlparse


class FacilitySeeder:

    def __init__(self, js_path: str, db_url: str):
        self.js_path = js_path
        self._params = self._parse_url(db_url)
        self._facilities = []

    @staticmethod
    def _parse_url(url: str) -> dict:
        parsed = urlparse(url)
        return {
            "host":     parsed.hostname,
            "port":     parsed.port or 5432,
            "database": parsed.path.lstrip("/"),
            "user":     parsed.username,
            "password": parsed.password,
            "ssl_context": True,
        }

    def load_from_js(self):
        with open(self.js_path, "r", encoding="utf-8") as f:
            src = f.read()
        src = re.sub(r"^const parkingData\s*=\s*", "", src.strip())
        src = re.sub(r";\s*$", "", src)
        self._facilities = json.loads(src)
        print(f"Loaded {len(self._facilities)} facilities from {self.js_path}")
        return self._facilities

    def seed(self, conn):
        if not self._facilities:
            raise RuntimeError("No facilities loaded — call load_from_js() first.")
        inserted = 0
        for f in self._facilities:
            conn.run(
                """INSERT INTO facilities (
                    osm_id, facility_name_clean, display_name,
                    latitude, longitude, zone, category, tier,
                    base_rate_kes, operating_hours, operating_schedule,
                    traffic_delay_index, parking_pressure_score, calibration_status,
                    overall_rating, security_score, accessibility_score,
                    price_transparency_score, estimated_capacity, distance_to_cbd_km,
                    tariff_model, payment_channels, penalty_fee_kes
                ) VALUES (
                    :osm_id, :name, :display,
                    :lat, :lon, :zone, :cat, :tier,
                    :rate, :hours, :schedule,
                    :tdi, :pps, :cal,
                    :rating, :sec, :acc,
                    :price_t, :cap, :dist,
                    :tariff, :payment, :penalty
                )
                ON CONFLICT (osm_id) DO UPDATE SET
                    display_name           = EXCLUDED.display_name,
                    parking_pressure_score = EXCLUDED.parking_pressure_score,
                    overall_rating         = EXCLUDED.overall_rating,
                    estimated_capacity     = EXCLUDED.estimated_capacity""",
                osm_id=f["osm_id"], name=f["facility_name_clean"], display=f["display_name"],
                lat=f["latitude"], lon=f["longitude"], zone=f.get("zone"), cat=f.get("category"),
                tier=f.get("tier"), rate=f.get("base_rate_kes"), hours=f.get("operating_hours"),
                schedule=f.get("operating_schedule"), tdi=f.get("traffic_delay_index"),
                pps=f.get("parking_pressure_score"), cal=f.get("calibration_status"),
                rating=f.get("overall_rating"), sec=f.get("security_score"),
                acc=f.get("accessibility_score"), price_t=f.get("price_transparency_score"),
                cap=f.get("estimated_capacity"), dist=f.get("distance_to_cbd_km"),
                tariff=f.get("tariff_model"), payment=f.get("payment_channels"),
                penalty=f.get("penalty_fee_kes"),
            )
            inserted += 1
        print(f"✓ Seeded {inserted} facilities successfully.")
        return inserted

    def run(self):
        self.load_from_js()
        conn = pg8000.native.Connection(**self._params)
        try:
            self.seed(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise SystemExit("ERROR: DATABASE_URL environment variable not set.")

    js_path = os.path.join(os.path.dirname(__file__), "parkingData.js")
    if not os.path.exists(js_path):
        raise SystemExit(f"ERROR: parkingData.js not found at {js_path}")

    seeder = FacilitySeeder(js_path=js_path, db_url=db_url)
    seeder.run()
