# ParkWise Nairobi: Data Documentation

## 1. Business Overview

Nairobi has a well documented parking shortage. A 2011 IBM commuter survey found that motorists in Nairobi spend an average of 31.7 minutes searching for a parking spot, compared with a 19.8 minute global average measured in the same study. A 2019 National Assembly Public Accounts Committee report found that Nairobi, a city with more than 1.3 million registered vehicles, had only around 6,125 formal parking spaces, most of them operated by Nairobi City County.

The county has since digitised parking fee payment through platforms such as nairobiservices.go.ke and the Nairobi Pay app, and a growing number of private ventures, including Spot Finder, Parksby, Naiparq, and KERB, now offer app based parking discovery and payment across zones such as the CBD, Westlands, Kilimani, and Upper Hill. None of these platforms, based on their public descriptions, tell a driver what will be available at a future time. They report what is listed, bookable, or reportedly open right now, not a forecast.

ParkWise Nairobi predicts, ahead of time, whether a given on-street facility is likely to be busier or quieter than its own typical pattern for a given hour and day type, built from real, accumulated traffic flow signals.

## 2. Problem Statement

Drivers in high demand Nairobi areas cannot currently plan a trip around parking availability in advance. They discover whether space exists only by arriving and circling, or by checking an app that reports current state rather than a forecast.

The central data challenge is that no public, official occupancy dataset exists for Nairobi parking facilities. Cities with an open, sensor based occupancy feed can train a prediction model directly against measured ground truth. Nairobi has no equivalent. This project is built around the closest defensible proxy for real demand, live traffic congestion, while being explicit at every stage about which numbers are measured, which are calibrated or documented estimates, and which are still missing.

## 3. Data Sources

| Source | What it provides | Nature of the data |
|---|---|---|
| OpenStreetMap, via the primary OSM API | Facility location, geometry, and whatever tags contributors have added | Real, but sparse. Most Nairobi parking facilities in OSM have no name and no capacity figure. |
| Nairobi City County Tariffs and Pricing Policy 2025-2030 | Zone I and Zone II on-street daily rates | Real, published rates, applied only to facilities confirmed as on-street |
| TomTom Traffic Flow API | Live road congestion at a facility's coordinates | Real, live signal. A demand pressure proxy, not a direct occupancy measurement |
| Field spot-check observations | Actual counted occupancy at a facility, on a specific date and time | Real ground truth, limited to what has been physically counted |
| Esri World Imagery | Satellite imagery per facility, used for desk based car counts | Real imagery. Capture date is unknown per tile and must never be treated as current |
| COWC (Cars Overhead With Context) | Approximately 32,700 annotated overhead car images, 15cm resolution | Real, published training data, Mundhenk et al., ECCV 2016. Contains no Nairobi data of any kind and is used only to train a car detection model |

## 4. Network Infrastructure Notes

During development, the Overpass API (the common third party interface to OpenStreetMap data, including overpass-api.de, overpass.kumi.systems, and maps.mail.ru mirrors) was found to be unreachable from the development network at a connection level, independent of query content. This was confirmed by testing all three mirrors directly and observing connection timeouts and refusals on each. OpenStreetMap's own primary API, api.openstreetmap.org, was confirmed reachable and is used throughout this pipeline instead, including a tiled fetch strategy for the initial facility extraction, since that endpoint enforces a per request bounding box size and node count limit not present in Overpass.

This is documented here so that a future maintainer encountering the same connection failures does not spend time attempting the same three mirrors again, and understands why the pipeline queries a bounding box in small tiles rather than in a single request.

## 5. Methodology, Stage by Stage

### 5.1 Facility extraction

All nodes and ways tagged `amenity=parking` within a Nairobi bounding box are pulled from OpenStreetMap. Unnamed facilities receive a coordinate based label rather than being dropped, so every row remains traceable to a real location.

### 5.2 Pricing assignment

Each facility is assigned a zone from the Nairobi City County Tariffs and Pricing Policy 2025-2030. On-street facilities receive the real, currently charged NCCG rate for their zone. Off-street facilities are matched to a named operator where the facility name allows it, and otherwise receive a documented placeholder rate, clearly labeled as an estimate rather than a verified figure. `pricing_source` records which of these applies for every row.

### 5.3 Sentiment scoring

Aspect scores for security, accessibility, price transparency, and overall rating are only computed when a working review data source exists. None currently does. Every sentiment column is left as a missing value across the dataset, flagged through `sentiment_data_source`, rather than filled with a placeholder rating.

### 5.4 Traffic signal

Live congestion is pulled from the TomTom Traffic Flow API and converted into `traffic_delay_index`, the ratio of free flow speed to current speed, floored at 1.0. Where no API key is present or a call fails, the relevant columns are left missing rather than filled with a fabricated value.

### 5.5 Scoping and tiering

The project narrows to facilities where `pricing_source` equals `NCCG_official_on_street`, meaning the facility carries a real, published county rate and is therefore confirmed on-street. A 2016 ITDP CBD Parking Survey found on-street parking running far more consistently full, 91 to 93 percent at peak, than off-street lots, 52 to 69 percent, in the same survey. This narrows the project toward the more genuinely scarce resource.

Scoped facilities are split into two validation tiers by distance to the CBD centroid. `tier1_cbd`, within 1.2 kilometres, receives a real but decade old, zone level historical occupancy reference from the same 2016 ITDP survey. `tier2_other` receives no occupancy reference of any kind, since none exists without a field visit.

### 5.6 Capacity estimation

No facility in the scoped set carries an OpenStreetMap capacity figure. Capacity is instead estimated using the same methodology as the 2016 ITDP survey: measuring real curb length from OpenStreetMap way geometry and dividing by approximately 5 metres per parallel parking space. Facilities mapped as a single point rather than a line segment are assumed to represent one informal space. If OpenStreetMap ever reports a real capacity figure directly, that value always overrides the estimate. `capacity_source` records which method produced each figure.

### 5.7 Satellite imagery collection

Esri World Imagery is queried for each scoped facility, starting at a 40 metre ground footprint and widening only where that resolution is not cached at a given location. Every image is logged in a manifest alongside the footprint actually used and an explicit note that capture date is unknown per tile. A human review pass marks each image as usable, too low resolution, or showing no parking, since a wide fallback footprint can be sharp while simply not containing the facility's actual parking segment.

### 5.8 Duplicate location clustering

OpenStreetMap frequently maps one continuous curb as several adjacent way objects. Proximity clustering groups facilities within 60 metres of each other into a shared cluster identifier, so that imagery review, manual counts, and any future calibration sampling treat one physical location as one unit rather than counting fragments as independent facilities.

### 5.9 Spot-check ground truth and the on-street gap

Real, hand entered field observations are the only data this project treats as ground truth for calibration. As of this documentation, ten real field observations exist, all at off-street facilities. None match an on-street facility in the scoped set. This means `parking_pressure_score`, a calibrated occupancy percentage, remains unpopulated for every on-street facility. This is a genuine, documented data gap, not an error in the pipeline.

An earlier version of the spot-check file was found to have been overwritten by a script that derived occupancy numbers directly from traffic data and relabeled them as field observations, a circularity that would have invalidated any calibration built on it. That script has been removed. The affected file version is retained, unmodified, for audit purposes. The current spot-check file contains only the genuinely recovered real observations.

### 5.10 Desk based occupancy estimates

Given the constraint that no field visits are conducted for this project, a desk based estimate can be built from the reviewed satellite imagery: a human verified car count in a usable image, divided by that facility's street length estimated capacity. Every row produced this way is explicitly labeled in its notes field as a desk based estimate, never presented as equivalent to a real field observation. A classical edge detection function assists this process by suggesting candidate car locations, but produces reliable false positives, shadows, roof edges, and road markings, and the logged count must always be a human verified correction, not the raw suggestion.

### 5.11 Relative availability signal

Since on-street calibration data does not exist, this project delivers a different, genuinely defensible prediction built entirely from the accumulated real traffic log: for each facility, how does its current reading compare to its own typical pattern at that hour and weekend status, based on repeated real TomTom snapshots collected over time. This requires no occupancy ground truth, since it only compares a facility to itself. The output is a real, defensible statement, for example that a facility is currently busier than its typical pattern for that hour and day type, rather than an unsupported absolute occupancy claim.

## 6. Evidence Tiers

Five distinct levels of evidence exist across this dataset and must never be blended together in analysis or reporting.

1. **parking_pressure_score.** Only ever populated from a real, fitted calibration against genuine spot-check data. Currently zero on-street facilities carry a value, since no real spot-check observation currently matches an on-street facility.
2. **historical_occupancy_reference_pct.** Real but zone level and decade old, from the 2016 ITDP survey. Available only for `tier1_cbd` facilities.
3. **relative_parking_pressure_index.** A live, real congestion signal, but a one moment relative ranking across facilities, not a calibrated occupancy estimate.
4. **relative_availability_signal and availability_label.** Live, real, and the project's actual delivered prediction. Each facility is compared only to its own historical pattern.
5. **estimated_capacity.** Either a real OpenStreetMap reported figure or a real street length based estimate using the ITDP 2016 methodology. Never a guess, but still an estimate wherever `capacity_source` is not an OpenStreetMap reported value.

## 7. Coverage Boundaries

The prediction described in this documentation applies only to the scoped on-street facility set. Off-street facilities, malls, hotels, and institutions, carry location and pricing data from earlier pipeline stages but were excluded from scope at the point their pricing could not be NCCG verified. They have no capacity estimate, no imagery, and no availability prediction. If these facilities are surfaced in a user facing application, they should be shown with location and price only, with no availability claim implied.

Nothing outside Nairobi exists in this dataset. The facility extraction query, the pricing logic, and the traffic collection infrastructure are all built specifically around Nairobi. Extending this pipeline to another city is architecturally straightforward, since the same stages, extraction, pricing mapping, traffic proxy, would apply, but this has not been built and is noted here as explicit future work rather than a silent gap.

## 8. Handoff to the CNN Car-Counting Component

A separate modeling effort trains a car detection model against the imagery collected in section 5.7.

**Training data.** `DetectionPatches_512x512_ALL.zip` from the COWC dataset, downloaded once and never modified. This contains no Nairobi data and teaches only what a car looks like from directly overhead.

**Target data.** The `esri_imagery` folder and its manifest, filtered to rows where `resolution_check_status` equals `usable`.

**Validation.** There is currently no independent Nairobi ground truth to validate detector accuracy against beyond whatever exists in the spot-check file. Detector accuracy, absent real Nairobi counts, can only be validated against COWC's own held out test set. This caveat should travel with any reported accuracy figure produced by this component.

## 9. Known Limitations

- No calibrated `parking_pressure_score` exists for any on-street facility, for the reasons detailed in section 5.9.
- Sentiment and review scores are unpopulated across the entire dataset, since no working review data source has been built.
- Satellite imagery capture dates are unknown per tile and must be treated as a single dated snapshot rather than a live reading.
- Coverage is limited to Nairobi, and within Nairobi to the on-street scope for prediction purposes, as detailed in section 7.
- The TomTom free tier provides no backfill for past conditions. Historical data exists only from the point repeated collection began.
