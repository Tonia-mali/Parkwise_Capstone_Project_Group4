# Parkwise_Capstone_Project_Group4
A smart parking prediction system for Nairobi that uses traffic, location, and parking data to predict parking pressure and provide an interactive map-based user interface.
# ParkWise Nairobi

A data pipeline and prediction system for on-street parking availability in Nairobi, built entirely from real, verifiable data sources. No occupancy figure in this project is invented. Every column is labeled with its source, so a reader can tell at a glance whether a number is measured, estimated from a documented methodology, or still missing.

## What this project does

ParkWise Nairobi predicts, ahead of time, whether an on-street parking facility is likely to be busier or quieter than its own typical pattern for a given hour and day type. The prediction is built from real, accumulated TomTom traffic congestion readings, compared against each facility's own historical baseline, not from a single current reading.

## Why this approach

No public occupancy dataset exists for Nairobi parking. Rather than simulate one, this project:

1. Scopes down to the subset of facilities with a real, published Nairobi City County parking rate (meaning they are confirmed on-street).
2. Estimates capacity from real street geometry using the same methodology as the 2016 ITDP CBD Parking Survey, since no facility in the scoped set has an OpenStreetMap capacity figure.
3. Uses live TomTom traffic congestion as a demand proxy, accumulated over repeated snapshots.
4. Builds a relative availability signal by comparing each facility's current reading against its own historical baseline at that hour and day type, rather than claiming an absolute occupancy percentage without ground truth to support it.

## Setup

1. Clone this repository.
2. Create the conda environment:
   or install directly with pip:
3. Copy `.env.example` to `.env` and add a real TomTom API key:
   Never commit `.env`. It is already listed in `.gitignore`.
4. Open `notebooks/parkwise_data_pipeline.ipynb` and run cells from the top.

## The CNN car-counting component

A separate modeling effort trains a car-detection model against the satellite imagery collected by this pipeline. It depends on two datasets that must not be confused with each other.

Training data: download `DetectionPatches_512x512_ALL.zip` from the COWC dataset at https://gdo152.llnl.gov/cowc/download/cowc-m/datasets/DetectionPatches_512x512_ALL.zip. This file is approximately 5.5GB and is not committed to this repository, since GitHub does not support files of this size. It contains real, generic overhead car imagery from outside Kenya, with no connection to Nairobi, used only to teach a model what a car looks like from directly overhead. Only this file variant is needed.

Target data: the `esri_imagery/` folder and `nairobi_esri_imagery_manifest.csv`, produced by the pipeline notebook. Only rows where `resolution_check_status` equals `usable` should be used for inference. Every image carries an unknown capture date per Esri's tile source, and this caveat must travel with any reported result.

There is currently no independent Nairobi ground truth to validate detector accuracy against beyond whatever exists in `nairobi_parking_spotcheck.csv`.

## Known data limitations

`parking_pressure_score`, a calibrated occupancy percentage, remains unpopulated for all on-street facilities. Real spot-check field data exists but only at off-street facilities, which do not match the on-street scope. This is documented in `docs/ParkWise_Data_Documentation.md`.

The project's actual delivered availability prediction is `relative_availability_signal` and `availability_label` in `nairobi_parking_traffic_log.csv`, built entirely from repeated real traffic readings compared against each facility's own history. This requires no occupancy ground truth.

Coverage is limited to Nairobi. Facilities outside the on-street scope have location and pricing data only, with no availability prediction. Nothing outside Nairobi exists in this dataset.

Sentiment and review scores are unpopulated across the dataset, reflected honestly through missing values rather than placeholder ratings.

## Data integrity note

A script that formerly overwrote `nairobi_parking_spotcheck.csv` with traffic derived numbers relabeled as ground truth has been removed from this project. The current `nairobi_parking_spotcheck.csv` holds only genuinely recovered real field observations.
