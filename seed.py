# seed.py — ParkWise Nairobi
# FacilitySeeder: loads parkingData.js and seeds all 500 facilities.
# Switched to psycopg2 for Python 3.14 compatibility.
#
# Usage:
#   DATABASE_URL=postgresql://... python seed.py

import os
import re
import json
import psycopg2


class FacilitySeeder:

    INSERT_SQL = """
        INSERT INTO facilities (
            osm_id, facility_name_clean, display_name,
            latitude, longitude, zone, category, tier,
            base_rate_kes, operating_hours, operating_schedule,
            traffic_delay_index, parking_pressure_score, calibration_status,
            overall_rating, security_score, accessibility_score,
            price_transparency_score, estimated_capacity, distance_to_cbd_km,
            tariff_model, payment_channels, penalty_fee_kes
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (osm_id) DO UPDATE SET
            display_name             = EXCLUDED.display_name,
            parking_pressure_score   = EXCLUDED.parking_pressure_score,
            overall_rating           = EXCLUDED.overall_rating,
            estimated_capacity       = EXCLUDED.estimated_capacity;
    """

    def __init__(self, js_path: str, dsn: str):
        self.js_path = js_path
        self.dsn = dsn
        self._facilities = []

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
        with conn.cursor() as cur:
            for f in self._facilities:
                cur.execute(self.INSERT_SQL, (
                    f["osm_id"], f["facility_name_clean"], f["display_name"],
                    f["latitude"], f["longitude"], f.get("zone"), f.get("category"), f.get("tier"),
                    f.get("base_rate_kes"), f.get("operating_hours"), f.get("operating_schedule"),
                    f.get("traffic_delay_index"), f.get("parking_pressure_score"),
                    f.get("calibration_status"), f.get("overall_rating"), f.get("security_score"),
                    f.get("accessibility_score"), f.get("price_transparency_score"),
                    f.get("estimated_capacity"), f.get("distance_to_cbd_km"),
                    f.get("tariff_model"), f.get("payment_channels"), f.get("penalty_fee_kes"),
                ))
                inserted += 1
        conn.commit()
        print(f"✓ Seeded {inserted} facilities successfully.")
        return inserted

    def run(self):
        self.load_from_js()
        conn = psycopg2.connect(self.dsn)
        try:
            self.seed(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("ERROR: DATABASE_URL environment variable not set.")
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    js_path = os.path.join(os.path.dirname(__file__), "parkingData.js")
    if not os.path.exists(js_path):
        raise SystemExit(f"ERROR: parkingData.js not found at {js_path}")

    seeder = FacilitySeeder(js_path=js_path, dsn=dsn)
    seeder.run()
