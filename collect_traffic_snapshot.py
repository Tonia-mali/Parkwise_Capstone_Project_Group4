"""
ParkWise Nairobi: scheduled traffic snapshot collector.

This is the same logic as the "Building a real training set" cell in
parkwise_data_pipeline_v2.ipynb, pulled out into a standalone script so it can be
scheduled to run automatically several times a day, instead of requiring someone to
open the notebook and click Run manually each time.

Each run:
  1. Reads the TomTom API key from a .env file (never hardcode it here).
  2. Pulls one live traffic reading per facility in the scoped on-street sample.
  3. Tags each reading with the real timestamp, hour, day of week, weekend flag,
     and Kenya public holiday flag at the moment the script runs.
  4. Applies whatever calibration currently exists from the spot-check file.
  5. Appends the results to nairobi_parking_traffic_log.csv.

It does not invent any values. If the API key is missing or a call fails, that row
is skipped or flagged, never filled in with a guess.

FACILITY SAMPLE: this now pulls all 93 verified on-street facilities from
nairobi_parking_onstreet_scope.csv (previously a 20-40 facility slice of the
full 500). That changes the safe scheduling interval -- see below.

SCHEDULING

Rate limit math: TomTom's free tier allows roughly 2,500 requests/day. With
93 facilities per run, that caps you at 2500 / 93 ~= 26 runs/day. Spread across
a 16-hour collection window (6 AM-10 PM), that's one run every ~37 minutes,
minimum. A 30-minute interval (48 runs/day) would need ~4,464 requests/day --
over budget. Use 45 minutes for a safe margin, or narrow the collection window.

Windows (Task Scheduler):
  1. Open Task Scheduler, "Create Basic Task".
  2. Trigger: Daily, then set it to repeat every 45 minutes during the hours you
     want coverage for (e.g. 6 AM to 10 PM), using the "Repeat task every" option
     under the trigger's Advanced Settings.
  3. Action: "Start a program".
     Program/script: path to your python.exe inside the ai-environment conda env,
     e.g. C:\\Users\\admin\\anaconda3\\New folder\\envs\\ai-environment\\python.exe
     Arguments: the full path to this script, e.g.
     C:\\Users\\admin\\path\\to\\collect_traffic_snapshot.py
     Start in: the project folder containing .env and the CSV files, so relative
     paths resolve correctly.

macOS/Linux (cron):
  Run `crontab -e` and add a line like:
    */45 6-22 * * * cd /path/to/project && /path/to/python collect_traffic_snapshot.py >> snapshot_log.txt 2>&1
  which runs every 45 minutes between 6 AM and 10 PM.

Either way, check in on it every day or two. A missed run just means a smaller
sample, not a broken pipeline, but the more real, spread-out runs you get before
your deadline, the better your eventual training data will be.
"""

import os
import time
import sys
from datetime import datetime

import subprocess
import sys

import numpy as np
import pandas as pd
import requests
import holidays
from dotenv import load_dotenv

TRAFFIC_LOG_PATH = "nairobi_parking_traffic_log.csv"
SPOTCHECK_PATH = "nairobi_parking_spotcheck.csv"
FACILITY_SAMPLE_PATH = "nairobi_parking_onstreet_scope.csv"  # scoped 93 on-street facilities
MIN_ROWS_FOR_CALIBRATION = 10

load_dotenv()
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")


def fetch_traffic_flow(lat, lon, api_key, session, timeout=5):
    url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {"point": f"{lat},{lon}", "key": api_key}
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()["flowSegmentData"]
        return {"current_speed": data["currentSpeed"], "free_flow_speed": data["freeFlowSpeed"]}
    except Exception:
        return None


def traffic_delay_index(current_speed, free_flow_speed, cap=3.0):
    if not current_speed or current_speed <= 0:
        return np.nan
    idx = free_flow_speed / current_speed
    return round(min(max(idx, 1.0), cap), 2)


def load_calibration():
    try:
        facilities = pd.read_csv(FACILITY_SAMPLE_PATH)
        spotcheck = pd.read_csv(SPOTCHECK_PATH)
    except FileNotFoundError:
        return None, None, 0

    merged = spotcheck.merge(
        facilities[["osm_id", "traffic_delay_index"]],
        left_on="facility_id",
        right_on="osm_id",
        how="inner"
    ).dropna(subset=["traffic_delay_index", "ground_truth_occupancy"])

    if len(merged) < MIN_ROWS_FOR_CALIBRATION:
        return None, None, len(merged)

    slope, intercept = np.polyfit(
        merged["traffic_delay_index"].values, 
        merged["ground_truth_occupancy"].values, 
        1
    )
    return slope, intercept, len(merged)


def collect_snapshot():
    if not TOMTOM_API_KEY:
        print(
            "No TOMTOM_API_KEY found. Check that .env exists in this folder with "
            "TOMTOM_API_KEY=your_key. Skipping this run rather than logging fabricated rows."
        )
        return None

    try:
        facilities = pd.read_csv(FACILITY_SAMPLE_PATH)  # all 93 scoped on-street facilities
    except FileNotFoundError:
        print(f"Could not find '{FACILITY_SAMPLE_PATH}'. Run the notebook pipeline through "
              "the on-street scoping step at least once before scheduling this script.")
        return None

    ke_holidays = holidays.country_holidays("KE", years=[datetime.now().year])
    now = datetime.now()
    slope, intercept, n_cal = load_calibration()

    session = requests.Session()
    rows = []
    for _, fac in facilities.iterrows():
        result = fetch_traffic_flow(fac["latitude"], fac["longitude"], TOMTOM_API_KEY, session)
        if result is None:
            delay_idx = np.nan
            source = "api_call_failed"
        else:
            delay_idx = traffic_delay_index(result["current_speed"], result["free_flow_speed"])
            source = "tomtom_flow_api"

        if slope is not None and pd.notna(delay_idx):
            pressure = round(float(np.clip(slope * delay_idx + intercept, 0, 100)), 1)
            calib_status = f"calibrated_n{n_cal}"
        else:
            pressure = np.nan
            calib_status = "not_calibrated_insufficient_spotcheck_data"

        rows.append({
            "facility_name": fac["facility_name_clean"],
            "latitude": fac["latitude"],
            "longitude": fac["longitude"],
            "collected_at": now.isoformat(timespec="seconds"),
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "is_weekend": int(now.weekday() >= 5),
            "is_holiday": int(now.date() in ke_holidays),
            "traffic_delay_index": delay_idx,
            "traffic_data_source": source,
            "parking_pressure_score": pressure,
            "calibration_status": calib_status,
        })
        time.sleep(0.25)

    df_new = pd.DataFrame(rows)
    if os.path.exists(TRAFFIC_LOG_PATH):
        df_existing = pd.read_csv(TRAFFIC_LOG_PATH)
        df_out = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_out = df_new

    df_out.to_csv(TRAFFIC_LOG_PATH, index=False)
    print(f"[{now.isoformat(timespec='seconds')}] Logged {len(df_new)} real snapshots. "
          f"Log now has {len(df_out)} total row(s).")
    if slope is None:
        print(f"Note: parking_pressure_score still NaN this run "
              f"(only {n_cal} calibration row(s), need {MIN_ROWS_FOR_CALIBRATION}).")
    return df_out


if __name__ == "__main__":
    result = collect_snapshot()
    sys.exit(0 if result is not None else 1)
