// Service Worker for POS System PWA
const CACHE_NAME = 'pos-cache-v2';
const OFFLINE_URL = '/offline/';

// Core static assets for POS offline app shell
const STATIC_CACHE_URLS = [
    '/',
    '/offline/',
    '/static/css/mobile-first.css',
    '/static/css/mobile-enhancements.css',
    '/static/css/pos-mobile.css',
    '/static/css/pos-desktop-optimized.css',
    '/static/css/pwa.css',
    '/static/css/custom-theme.css',
    '/static/css/pos-ui.css',
    '/static/css/button-checkbox-fixes.css',
    '/static/css/checkbox-override.css',
    '/static/css/calculator_widget.css',
    '/static/js/pwa-install.js',
    '/static/js/offline-db.js',
    '/static/js/sync-manager.js',
    '/static/js/calculator_widget.js',
    '/static/js/pos-keyboard-shortcuts.js',
    '/static/images/icon-192.png',
    '/static/images/icon-512.png',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
];

// Install event - pre-cache critical assets
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing POS Cache v2...');
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            console.log('[Service Worker] Pre-caching app shell assets');
            // Cache items individually so one failure does not break the entire cache
            for (const url of STATIC_CACHE_URLS) {
                try {
                    await cache.add(url);
                } catch (err) {
                    console.warn('[Service Worker] Failed to cache:', url, err);
                }
            }
        })
    );
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating POS Cache v2...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Deleting outdated cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event - smart routing (Network-First for HTML navigation, Stale-While-Revalidate for static assets)
self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') {
        return;
    }

    const requestUrl = new URL(event.request.url);

    // Skip chrome-extension / non-http URLs
    if (!event.request.url.startsWith('http')) {
        return;
    }

    // Dynamic APIs and endpoints that should always hit network
    const isDynamicAPI = requestUrl.pathname.startsWith('/api/') || 
                         requestUrl.pathname.includes('/sync/') || 
                         requestUrl.pathname.includes('/ping/') || 
                         requestUrl.searchParams.has('load_products') || 
                         requestUrl.searchParams.has('get_prices');

    if (isDynamicAPI) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(JSON.stringify({ 
                    offline: true, 
                    error: 'Network unreachable. Utilizing local offline storage.' 
                }), {
                    headers: { 'Content-Type': 'application/json' }
                });
            })
        );
        return;
    }

    // 1. Navigation requests (HTML pages) -> Network-first with cached shell fallback
    if (event.request.mode === 'navigate' || event.request.destination === 'document') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    if (response && response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, copy);
                        });
                    }
                    return response;
                })
                .catch(async () => {
                    const cachedResponse = await caches.match(event.request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    // Fallback to POS home shell or offline page
                    const posShell = await caches.match('/');
                    if (posShell) return posShell;
                    return caches.match(OFFLINE_URL);
                })
        );
        return;
    }

    // 2. Static Assets (CSS, JS, Images, Fonts) -> Stale-While-Revalidate
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            const fetchPromise = fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const copy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, copy);
                    });
                }
                return networkResponse;
            }).catch(() => {
                // If offline and not in cache, return empty/cached asset if available
                return cachedResponse;
            });

            return cachedResponse || fetchPromise;
        })
    );
});

// Background Sync Listener
self.addEventListener('sync', (event) => {
    console.log('[Service Worker] Background sync event triggered:', event.tag);
    if (event.tag === 'sync-sales' || event.tag === 'sync-all') {
        event.waitUntil(notifyClientsToSync());
    }
});

async function notifyClientsToSync() {
    const clients = await self.clients.matchAll();
    clients.forEach((client) => {
        client.postMessage({
            type: 'TRIGGER_SYNC_NOW',
            timestamp: Date.now()
        });
    });
}
