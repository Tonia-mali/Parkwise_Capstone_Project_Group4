const CACHE_NAME = 'parkwise-cache-v1';
const ASSETS_TO_CACHE = [
    './',
    './index.html',
    './style.css',
    './app.js',
    './facilities.js'
];

// Install Event: Caches all our core files
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('Caching App Assets');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

// Fetch Event: Serves the app from cache if network drops
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request);
        })
    );
});