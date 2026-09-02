# README.md

# ParkWise: AI-Driven Overhead Car Counting & Parking Occupancy Pipeline

## Business & Problem Overview

Urban centers such as Nairobi face significant traffic congestion, inefficient space utilization, and lost productivity due to drivers manually searching for available parking spaces. **ParkWise** provides an automated, scalable computer vision solution that converts high-resolution overhead/satellite imagery into real-time, actionable parking availability insights.

By estimating localized vehicle counts directly from aerial image patches, ParkWise calculates dynamic occupancy fractions for designated parking facilities across the city, reducing driver search times and helping lot operators optimize space.

---

## Technical Approach & Methodological Solution

### 1. Model Selection & Architecture

* **Model Backbone:** Modified **ResNet-18** Deep Convolutional Neural Network.


* **Task Formulation:** Continuous scalar regression (direct estimation of car counts per image patch) rather than bounding-box detection, allowing faster inference across massive aerial scenes.


* **Custom Regression Head:** Replaced the default 1,000-class classification head with a dense feed-forward network:

$$\text{Linear}(512 \to 128) \implies \text{ReLU} \implies \text{Dropout}(0.2) \implies \text{Linear}(128 \to 1)$$



* **Why ResNet-18?** ResNet-18 provides residual connections that prevent gradient vanishing while maintaining low memory overhead and high throughput. This balance makes it ideal for sliding-window batch processing over high-resolution imagery.



### 2. Dataset & Training Strategy

* **Training Source:** Cars Overhead With Context (**COWC**) dataset (`DetectionPatches_512x512_ALL`).


* **Target Aggregation:** Aggregated vehicle sub-categories (`Sedan_Count`, `Pickup_Count`, `Other_Count`, `Unknown_Count`) into a unified continuous target variable `Total_Car_Count`.


* **Spatial Hold-Out Split:** To evaluate generalization across unseen geographic terrains, patches from the **Potsdam** region were reserved as a spatial hold-out test set ($32,136$ training patches vs $637$ test patches).


* **Imbalance Handling:** Due to high background zero-car patch density ($64.4\%$ zero-car patches), a `WeightedRandomSampler` was implemented to balance loss updates evenly between background and vehicle-dense patches.


* **Optimization & Loss Function:**
* **Loss Function:** Mean Absolute Error ($\text{L1 Loss}$) to reduce sensitivity to extreme outliers.


* **Optimizer:** `AdamW` ($\text{lr} = 10^{-4}$, $\text{weight\_decay} = 10^{-4}$) over 15 training epochs.





### 3. Inference Engine (Nairobi Satellite Integration)

* **Sliding Window & Padded Patching:** High-resolution satellite images of Nairobi lots are cropped into continuous patches ($224 \times 224$ or padded $512 \times 512$ tiles).


* **Batch Processing & Clamping:** Patches are evaluated in parallel batches (`BATCH_SIZE = 16` or `32`), with outputs clamped at zero ($\max(0, \hat{y})$) to enforce non-negative vehicle estimations.


* **Occupancy Fraction Calculation:**

$$\text{Occupancy Fraction} = \min\left(\frac{\sum \text{Predicted Cars}}{\text{Facility Capacity}}, 1.0\right)$$




---

## Model Outputs & Performance Results

### Model Performance Benchmarks

During training and validation across 15 epochs, the model converged smoothly, achieving its target evaluation metric:

| Metric | Target Limit | Achieved Best Result | Epoch |
| --- | --- | --- | --- |
| **Test Mean Absolute Error (MAE)** | $\le 2.50$ cars/patch | **1.902** cars/patch

 | Epoch 9

 |
| **Final Epoch Test MAE** | $\le 2.50$ cars/patch | **1.971** cars/patch

 | Epoch 15

 |~~~~~~~~

### Inference Outputs (Sample Spotcheck Evaluation)

Upon evaluating Nairobi imagery files (such as 95 captured parking lot scenes), the pipeline produces output metrics mapped back to real-world parking spots and saved to `nairobi_parking_spotcheck.csv`:

* **Indexed Imagery Processed:** 95 images


* **Target Spotcheck Rows Updated:** 22 parking locations


* **Sample Facility Metric Output:**
* **Facility:** CBD Holy Family Basement / Nairobi Spot Coordinates


* **Estimated Cars Detected:** $\approx 49.7$ cars

~~~~
* **Facility Capacity:** 100


* **Calculated Occupancy Rate:** $49.71\%$




---

## Artifacts & Directory Structure

```text
parkwise/
├── DetectionPatches_512x512_ALL/   # COWC Overhead Patch Dataset
│   └── object_count.csv             # Ground truth count annotations
├── Images/                          # High-res satellite imagery for Nairobi
├── model1_artifacts/
│   └── parkwise_model1_resnet18.pt  # Saved PyTorch checkpoint (Best MAE: 1.902)
├── parkwise_final_maybe/
│   └── nairobi_parking_spotcheck.csv# Updated occupancy fractions
├── parkwise_occupancy_model.joblib  # Production ML model package
└── parkwise_model_metadata.joblib   # Scalers, feature names, & run metadata

```