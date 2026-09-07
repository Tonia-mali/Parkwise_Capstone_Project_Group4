# seed.py — ParkWise Nairobi
# FacilitySeeder class: loads parkingData.js and seeds all 500 facilities
# into PostgreSQL. Run once after schema.sql has been applied.
#
# Usage:
#   DATABASE_URL=postgresql://... python seed.py

import os
import re
import json
import asyncio
import asyncpg


class FacilitySeeder:
    """
    Loads facility records from parkingData.js and inserts them into
    the PostgreSQL facilities table.

    Responsibilities are split across three methods:
      load_from_js()  — reads and parses the JS file into Python dicts
      seed()          — inserts records into the database
      run()           — orchestrates both (the public entry point)
    """

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
            $1, $2, $3,
            $4, $5, $6, $7, $8,
            $9, $10, $11,
            $12, $13, $14,
            $15, $16, $17,
            $18, $19, $20,
            $21, $22, $23
        )
        ON CONFLICT (osm_id) DO UPDATE SET
            display_name              = EXCLUDED.display_name,
            parking_pressure_score    = EXCLUDED.parking_pressure_score,
            overall_rating            = EXCLUDED.overall_rating,
            estimated_capacity        = EXCLUDED.estimated_capacity;
    """

    def __init__(self, js_path: str, dsn: str):
        """
        Args:
            js_path: Path to parkingData.js
            dsn:     PostgreSQL connection string (postgresql://...)
        """
        self.js_path = js_path
        self.dsn = dsn
        self._facilities: list[dict] = []

    # ── Load ──────────────────────────────────────────────────────────────────

    def load_from_js(self) -> list[dict]:
        """
        Read parkingData.js, strip the JS wrapper, and parse the
        array as JSON. Returns the list of facility dicts and stores
        them internally for use by seed().
        """
        with open(self.js_path, "r", encoding="utf-8") as f:
            src = f.read()

        # Strip: const parkingData = [ ... ];
        src = re.sub(r"^const parkingData\s*=\s*", "", src.strip())
        src = re.sub(r";\s*$", "", src)

        self._facilities = json.loads(src)
        print(f"Loaded {len(self._facilities)} facilities from {self.js_path}")
        return self._facilities

    # ── Seed ──────────────────────────────────────────────────────────────────

    async def seed(self, conn: asyncpg.Connection) -> int:
        """
        Insert all loaded facilities into PostgreSQL inside a single
        transaction. Returns the number of records inserted.
        Requires load_from_js() to have been called first.
        """
        if not self._facilities:
            raise RuntimeError("No facilities loaded — call load_from_js() first.")

        inserted = 0
        async with conn.transaction():
            for f in self._facilities:
                await conn.execute(
                    self.INSERT_SQL,
                    f["osm_id"],
                    f["facility_name_clean"],
                    f["display_name"],
                    f["latitude"],
                    f["longitude"],
                    f.get("zone"),
                    f.get("category"),
                    f.get("tier"),
                    f.get("base_rate_kes"),
                    f.get("operating_hours"),
                    f.get("operating_schedule"),
                    f.get("traffic_delay_index"),
                    f.get("parking_pressure_score"),
                    f.get("calibration_status"),
                    f.get("overall_rating"),
                    f.get("security_score"),
                    f.get("accessibility_score"),
                    f.get("price_transparency_score"),
                    f.get("estimated_capacity"),       # nullable
                    f.get("distance_to_cbd_km"),
                    f.get("tariff_model"),
                    f.get("payment_channels"),
                    f.get("penalty_fee_kes"),
                )
                inserted += 1

        print(f"✓ Seeded {inserted} facilities successfully.")
        return inserted

    # ── Run (public entry point) ───────────────────────────────────────────────

    async def run(self) -> None:
        """Load the JS file then connect and seed the database."""
        self.load_from_js()
        conn = await asyncpg.connect(self.dsn)
        try:
            await self.seed(conn)
        finally:
            await conn.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

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
    asyncio.run(seeder.run())
