// --- BROWSER VOICE BUG FIX ---
let globalVoices = [];
window.speechSynthesis.onvoiceschanged = () => {
    globalVoices = window.speechSynthesis.getVoices();
};
globalVoices = window.speechSynthesis.getVoices();

// 1. Map Layers Setup (UPGRADED TO GOOGLE MAPS CLONE)
const googleStreets = L.tileLayer('http://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
    maxZoom: 20,
    subdomains:['mt0','mt1','mt2','mt3'],
    attribution: 'Map data © Google'
});

const googleSatellite = L.tileLayer('http://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {
    maxZoom: 20,
    subdomains:['mt0','mt1','mt2','mt3'],
    attribution: 'Imagery © Google'
});

// 2. Initialize Map
let userLat = -1.2833; 
let userLon = 36.8167;
let userMarker = null;
let currentRoute = null;
let watchId = null; 
let isDrivingMode = false;

const map = L.map('map', {
    center: [userLat, userLon],
    zoom: 14,
    layers: [googleStreets] // Now defaults to Google Maps look!
});

// Add Layer Control
L.control.layers({
    "Google Streets": googleStreets,
    "Google Satellite": googleSatellite
}).addTo(map);

// 3. User Location Functions
function setUserLocation(lat, lon) {
    userLat = lat;
    userLon = lon;
    
    if (userMarker) {
        map.removeLayer(userMarker);
    }
    
    userMarker = L.circleMarker([userLat, userLon], {
        radius: 9,
        fillColor: '#4285F4', // Google Blue
        color: '#ffffff',
        weight: 3,
        opacity: 1,
        fillOpacity: 1
    }).addTo(map).bindPopup("<b>📍 You Are Here</b>");
}

setUserLocation(userLat, userLon);

if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
        (position) => {
            setUserLocation(position.coords.latitude, position.coords.longitude);
            map.setView([position.coords.latitude, position.coords.longitude], 15);
        },
        (error) => console.warn("Geolocation access denied.")
    );
}

// 4. Mathematical Helper
function calculateDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371; 
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

// 5. Route to Nearest Spot
function routeToNearestSpot() {
    let nearestFacility = null;
    let minDistance = Infinity;

    parkingData.forEach(facility => {
        if (facility.latitude && facility.longitude) {
            const distance = calculateDistanceKm(userLat, userLon, facility.latitude, facility.longitude);
            if (distance < minDistance) {
                minDistance = distance;
                nearestFacility = facility;
            }
        }
    });

    if (nearestFacility) {
        calculateRoute(nearestFacility.latitude, nearestFacility.longitude, nearestFacility);
    }
}

// 6. Female Voice Helper
function speakWithFemaleVoice(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); 
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9; 
        utterance.pitch = 1.2; 

        let voices = globalVoices.length > 0 ? globalVoices : window.speechSynthesis.getVoices();
        let femaleVoice = voices.find(voice => 
            voice.name.includes('Zira') || voice.name.includes('Samantha') || 
            voice.name.includes('Female') || voice.name.toLowerCase().includes('woman')
        );

        if (femaleVoice) utterance.voice = femaleVoice;
        window.speechSynthesis.speak(utterance);
    }
}

// 7. Multi-Route Engine (Car Routing Only for Free Open-Source)
function calculateRoute(destLat, destLon, facility = null) {
    if (currentRoute) map.removeControl(currentRoute);

    currentRoute = L.Routing.control({
        waypoints: [ L.latLng(userLat, userLon), L.latLng(destLat, destLon) ],
        routeWhileDragging: false,
        addWaypoints: false,
        showAlternatives: true, 
        altLineOptions: { styles: [{color: '#94a3b8', opacity: 0.6, weight: 5}] },
        lineOptions: { styles: [{color: '#4285F4', opacity: 0.85, weight: 6}] }, // Google Blue route line
        fitSelectedRoutes: true
    }).addTo(map);

    currentRoute.on('routesfound', function(e) {
        const routes = e.routes;
        const summary = routes[0].summary;
        const firstInstruction = routes[0].instructions[0].text;
        const distKm = (summary.totalDistance / 1000).toFixed(1);
        
        let speechText = "";
        
        if (facility) {
            const spokenName = facility.facility_name_clean.replace(/\s*\(.*?\)/g, '').trim();
            const bays = facility.capacity && !isNaN(facility.capacity) ? facility.capacity : 'unlisted';
            const rate = facility.base_rate_kes === 'Unknown' ? 'unknown' : facility.base_rate_kes + ' shillings';
            
            speechText = `Navigating to ${spokenName}. Distance is ${distKm} kilometers. Pricing is ${rate}. Capacity is ${bays} bays. Next instruction: ${firstInstruction}.`;
        } else {
            speechText = `Route found. Distance is ${distKm} kilometers. ${firstInstruction}.`;
        }
        
        speakWithFemaleVoice(speechText);
    });
}

// 8. Styling & Markers
function getPressureColor(delayIndex) {
    if (delayIndex > 2.0) return '#ea4335'; // Google Red
    if (delayIndex > 1.3) return '#fbbc05'; // Google Yellow
    return '#34a853';                       // Google Green
}

function getMarkerStyle(facility) {
    const isCalibrated = facility.calibration_status === "calibrated";
    return {
        radius: 6, fillColor: getPressureColor(facility.traffic_delay_index),
        color: isCalibrated ? '#000000' : '#ffffff', weight: isCalibrated ? 2 : 1.5,
        opacity: 1, fillOpacity: 0.9, dashArray: isCalibrated ? null : '4, 4'
    };
}

window.routeToFacility = function(index) {
    const facility = parkingData[index];
    calculateRoute(facility.latitude, facility.longitude, facility);
};

parkingData.forEach((facility, index) => {
    if (facility.latitude && facility.longitude) {
        const marker = L.circleMarker([facility.latitude, facility.longitude], getMarkerStyle(facility));
        const rating = facility.overall_rating && !isNaN(facility.overall_rating) ? `⭐ ${Number(facility.overall_rating).toFixed(1)}/5.0` : 'No reviews yet';
        
        let popupHTML = `
            <div style="font-family: Arial, sans-serif; min-width: 220px; font-size: 13px; line-height: 1.4;">
                <h4 style="margin: 0 0 6px 0; color: #1e293b;">${facility.facility_name_clean.replace(/\s*\(.*?\)/g, '')}</h4>
                <b>💰 Base Rate:</b> Ksh ${facility.base_rate_kes}<br>
                <b>⭐ Rating:</b> ${rating}<br>
                <b>📊 Traffic Delay Index:</b> ${Number(facility.traffic_delay_index).toFixed(2)}<br>
                <button onclick="routeToFacility(${index})" 
                        style="margin-top: 8px; width: 100%; padding: 7px; background: #4285F4; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                    🚗 Route to this Spot
                </button>
            </div>
        `;
        marker.bindPopup(popupHTML);
        marker.addTo(map);
    }
});

// 9. Interactive Functions
function clearRoute() {
    if (currentRoute) {
        map.removeControl(currentRoute);
        currentRoute = null;
    }
}

// LIVE DRIVING MODE FUNCTION
function toggleDriveMode() {
    isDrivingMode = !isDrivingMode;
    const btn = document.getElementById('driveModeBtn');
    
    if (isDrivingMode) {
        btn.style.background = '#ea4335'; // Red to stop
        btn.innerHTML = '🛑 Stop Drive Mode';
        
        if (navigator.geolocation) {
            watchId = navigator.geolocation.watchPosition(
                (position) => {
                    setUserLocation(position.coords.latitude, position.coords.longitude);
                    map.setView([position.coords.latitude, position.coords.longitude], 17); 
                },
                (error) => alert("Cannot track live location. Ensure GPS is on."),
                { enableHighAccuracy: true, maximumAge: 0 }
            );
        }
    } else {
        btn.style.background = '#4285F4'; // Blue to start
        btn.innerHTML = '🚙 Start Drive Mode';
        if (watchId) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
        }
    }
}

// 10. Floating Quick Action Controls
const quickActionControl = L.control({ position: 'topright' });
quickActionControl.onAdd = function () {
    const div = L.DomUtil.create('div', 'leaflet-control');
    div.style.display = 'flex';
    div.style.flexDirection = 'column';
    div.style.gap = '8px';
    
    div.innerHTML = `
        <button onclick="routeToNearestSpot()" 
                style="background: #34a853; color: white; padding: 10px 14px; font-weight: bold; border: none; cursor: pointer; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-size: 13px;">
            ⚡ Find Nearest Parking
        </button>
        <button id="driveModeBtn" onclick="toggleDriveMode()" 
                style="background: #4285F4; color: white; padding: 10px 14px; font-weight: bold; border: none; cursor: pointer; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-size: 13px;">
            🚙 Start Drive Mode
        </button>
        <button onclick="clearRoute()" 
                style="background: #ea4335; color: white; padding: 10px 14px; font-weight: bold; border: none; cursor: pointer; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-size: 13px;">
            ❌ Exit Route
        </button>
    `;
    return div;
};
quickActionControl.addTo(map);