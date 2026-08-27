# ParkWise Nairobi: On-Street Scoping and Data State

Last updated: 26 August 2026

## 1. Why scoping exists

The project's real external validation source, the [ITDP / University of Nairobi 2016
CBD Parking Survey](https://africa.itdp.org/wp-content/uploads/2021/04/Nairobi-CBD-Parking-Survey-160613.pdf),
only surveyed on-street parking within the Nairobi CBD core. Its published occupancy
figures (roughly 91-93% at peak, across three CBD zones) are a legitimate sanity-check
reference only for facilities that actually sit within that surveyed area. Applying it to
an on-street spot several kilometres away, or to an off-street mall or hotel lot, would
not be defensible.

Scoping and tiering keeps that reference attached only where it's actually valid.

## 2. What the scoping step does

`nairobi_parking_onstreet_scope.csv` is generated from `nairobi_parking_master_dataset.csv`
by filtering to `category == "On-Street"` (93 of the 500 facilities), then:

1. Computing each facility's real haversine distance to the CBD centre (GPO Nairobi /
   Kenyatta Avenue, `-1.2833, 36.8167`).
2. Splitting into two tiers:
   - **`tier1_cbd`**: 21 facilities within 1.2 km of the CBD centre.
   - **`tier2_other`**: 72 facilities beyond that radius.
   - There is a clean gap between tiers (nearest tier2 facility is 1.258 km out, farthest
     tier1 facility is 1.154 km in) -- no facility sits ambiguously at the boundary.
3. Attaching `historical_occupancy_reference_pct = 92.0` (the ITDP survey's approximate
   on-street peak occupancy, Table 3-5) **only to `tier1_cbd`**. `tier2_other` gets `NaN`
   and `historical_reference_source = "not_applicable_outside_surveyed_area"`.
4. Computing `relative_parking_pressure_index` for all 93: `traffic_delay_index` rescaled
   0-100 within this on-street subset. This is a live, real signal, but explicitly relative
   and uncalibrated -- it is not an occupancy percentage and should never be reported as one.
5. Initializing `parking_pressure_score` as empty (`NaN`) and `calibration_status` as
   `not_calibrated_insufficient_spotcheck_data`. This column is reserved exclusively for a
   value fit against real spot-check ground truth.

## 3. The current gap: no on-street ground truth yet

As of this writing, `nairobi_parking_spotcheck.csv` has 10 real observations, but **all 10
are at off-street facilities** (a hotel car park, a mall car park, a bus terminus, and
generic off-street spots). None match an on-street `osm_id`.

Practical effect: `parking_pressure_score` is empty for all 93 on-street facilities, and
will stay that way until at least a handful of real on-street spot-check observations are
collected. This is a genuine data gap, not a bug in the pipeline -- the calibration cell
correctly reports `not_calibrated_insufficient_matched_data` rather than fabricating a fit.

**Recommended next step:** collect 5-10 real spot-check observations specifically at
on-street facilities (ideally a mix of `tier1_cbd` and `tier2_other`), so the calibration
step has something real to fit against.

## 4. Evidence levels -- do not blend these when reporting results

| Column | What it is | What it is not |
|---|---|---|
| `historical_occupancy_reference_pct` | Real, published ITDP 2016 figure, `tier1_cbd` only | Not current-day ground truth; it's 10 years old and geographically limited |
| `relative_parking_pressure_index` | Real, live TomTom-derived signal, all 93 facilities | Not a calibrated or absolute occupancy estimate |
| `parking_pressure_score` | The only column meant to represent a calibrated estimate | Currently empty for all on-street facilities -- there is no real fit yet |

Any report, slide, or write-up describing on-street parking pressure should state plainly
which of these three columns a number comes from. Presenting `relative_parking_pressure_index`
as if it were `parking_pressure_score`, or treating the 2016 ITDP figure as current
measurement, would misrepresent what the data actually supports.

## 5. Rate limit note for the snapshot collector

`collect_traffic_snapshot.py` and the matching notebook cell now pull all 93 scoped
on-street facilities per run (previously a 20-40 facility slice of the full 500 dataset).
TomTom's free tier allows roughly 2,500 requests/day: 93 facilities x 48 runs/day (a
30-minute interval) would need ~4,464 requests/day, over budget. **Use a 45-minute
interval** for a safe margin, or narrow the active collection window.

## 6. Open item: `generate_synthetic_prototyping_data.py`

This script and `nairobi_parking_SYNTHETIC_prototyping_only.csv` still exist in the
project, built around the assumption that synthetic rows would eventually be replaced by
real field-collected spot-checks. Since the current plan does not include a full field
campaign, whether to keep, repurpose, or remove this script is a decision the team should
make explicitly rather than leave ambiguous -- it has not been changed as part of this
update.
