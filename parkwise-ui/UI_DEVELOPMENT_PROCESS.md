# UI Development & Frontend Engineering Process

## Overview
This document outlines the frontend development process for the ParkWise Nairobi Occupancy map. The goal was to build a highly interactive, scalable, and mobile-friendly user interface that visualizes parking predictions while providing real-world utility like routing and voice navigation.

## Engineering Decisions & Implementations

### 1. Mapping Infrastructure
*   **Engine:** We utilized Leaflet.js for our core mapping engine due to its lightweight nature and open-source flexibility.
*   **Tileset:** To provide a familiar and premium user experience, we integrated Google Maps tile layers, allowing users to toggle seamlessly between standard "Google Streets" and high-resolution "Google Satellite" views.

### 2. Mock Data Pipeline (Frontend/Backend Decoupling)
*   To ensure UI development was not blocked by backend API construction, we built a Python script to convert our master dataset into a static JavaScript file (`facilities.js`).
*   This acts as a mock backend. Once the live machine learning API is deployed by the data team, this local file will be replaced with a standard `fetch()` request, allowing the UI to instantly scale across Nairobi and the rest of Africa.

### 3. Navigation & Routing Engine
*   **Routing:** We implemented the Leaflet Routing Machine (OSRM) to calculate accurate driving distances and generate turn-by-turn alternative routes.
*   **Nearest Spot Algorithm:** We built a custom function using the Haversine formula to calculate the straight-line distance between the user's live GPS coordinates and all dataset facilities, instantly identifying and routing to the closest available parking.
*   **Live Tracking:** Integrated the browser's `geolocation.watchPosition` API to create a "Live Drive Mode" that locks the camera to the user's moving vehicle.

### 4. Accessibility & Voice Guidance
*   Integrated the native Web Speech API to provide hands-free voice navigation. 
*   Wrote custom filtering logic to search the user's device for natural-sounding female voices.
*   Configured the speech engine to dynamically read out critical facility statistics (Pricing, Capacity, Traffic Delay Index) alongside driving instructions, while filtering out raw GPS coordinate text for a cleaner audio experience.

### 5. Progressive Web App (PWA) Conversion
*   Instead of building separate, costly native apps for Android and iOS, we converted the web map into a Progressive Web App (PWA).
*   Configured a `manifest.json` for app iconography and theme coloring.
*   Implemented a Service Worker (`sw.js`) to cache core assets. This allows users to "Install" the web app directly to their smartphone home screens for a native app experience without app store deployment.