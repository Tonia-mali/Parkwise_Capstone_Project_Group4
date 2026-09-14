-- ParkWise Nairobi — PostgreSQL Schema
-- Run this once against your Render PostgreSQL database to create all tables.

-- ─────────────────────────────────────────
-- 1. FACILITIES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facilities (
    osm_id                  BIGINT          PRIMARY KEY,
    facility_name_clean     TEXT            NOT NULL,
    display_name            TEXT            NOT NULL,
    latitude                NUMERIC(10, 7)  NOT NULL,
    longitude               NUMERIC(10, 7)  NOT NULL,
    zone                    TEXT,
    category                TEXT,
    tier                    TEXT,
    base_rate_kes           INTEGER,
    operating_hours         TEXT,
    operating_schedule      TEXT,
    traffic_delay_index     NUMERIC(5, 2),
    parking_pressure_score  NUMERIC(5, 2),
    calibration_status      TEXT,
    overall_rating          NUMERIC(3, 1),
    security_score          NUMERIC(3, 1),
    accessibility_score     NUMERIC(3, 1),
    price_transparency_score NUMERIC(3, 1),
    estimated_capacity      INTEGER,                  -- nullable: many facilities have no capacity data
    distance_to_cbd_km      NUMERIC(6, 3),
    tariff_model            TEXT,
    payment_channels        TEXT,
    penalty_fee_kes         INTEGER,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- 2. DEMAND PREDICTIONS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS demand_predictions (
    id              SERIAL          PRIMARY KEY,
    osm_id          BIGINT          NOT NULL REFERENCES facilities(osm_id) ON DELETE CASCADE,
    predicted_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    hour_of_day     SMALLINT        NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    day_of_week     SMALLINT        NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),  -- 0=Monday
    pressure_score  NUMERIC(5, 2),  -- HistGradientBoosting output
    demand_level    TEXT            -- e.g. 'low', 'medium', 'high' — derived from pressure_score
);

CREATE INDEX IF NOT EXISTS idx_demand_osm_id ON demand_predictions(osm_id);
CREATE INDEX IF NOT EXISTS idx_demand_predicted_at ON demand_predictions(predicted_at DESC);

-- ─────────────────────────────────────────
-- 3. CNN COUNTS  (stub — Person 3 not ready)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cnn_counts (
    id              SERIAL          PRIMARY KEY,
    osm_id          BIGINT          NOT NULL REFERENCES facilities(osm_id) ON DELETE CASCADE,
    counted_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    car_count       INTEGER,        -- ResNet-18 regression output (single value)
    image_source    TEXT            -- optional: URL or path of the image used for inference
);

CREATE INDEX IF NOT EXISTS idx_cnn_osm_id ON cnn_counts(osm_id);

-- ─────────────────────────────────────────
-- 4. USERS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL          PRIMARY KEY,
    email           TEXT            UNIQUE,           -- nullable for guest users
    password_hash   TEXT,                             -- nullable for guest users
    is_guest        BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
