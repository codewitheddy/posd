// Service Worker for POS System PWA
const CACHE_NAME = 'pos-cache-v1';
const OFFLINE_URL = '/offline/';

// Files to cache for offline use
const STATIC_CACHE_URLS = [
    '/',
    '/static/css/pos-mobile.css',
    '/static/css/mobile-first.css',
    '/static/js/bootstrap.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[Service Worker] Caching static assets');
            return cache.addAll(STATIC_CACHE_URLS).catch((error) => {
                console.error('[Service Worker] Cache addAll error:', error);
            });
        })
    );
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }

    // Skip chrome extensions and other non-http requests
    if (!event.request.url.startsWith('http')) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                // Return cached version
                return cachedResponse;
            }

            // Try to fetch from network
            return fetch(event.request)
                .then((response) => {
                    // Don't cache non-successful responses
                    if (!response || response.status !== 200 || response.type === 'error') {
                        return response;
                    }

                    // Clone the response
                    const responseToCache = response.clone();

                    // Cache successful responses (except API calls)
                    if (!event.request.url.includes('/api/')) {
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseToCache);
                        });
                    }

                    return response;
                })
                .catch(() => {
                    // Network failed, return offline page for navigation requests
                    if (event.request.mode === 'navigate') {
                        return caches.match(OFFLINE_URL);
                    }
                });
        })
    );
});

// Background sync for offline sales
self.addEventListener('sync', (event) => {
    console.log('[Service Worker] Background sync:', event.tag);
    
    if (event.tag === 'sync-sales') {
        event.waitUntil(syncOfflineSales());
    }
});

// Sync offline sales when back online
async function syncOfflineSales() {
    try {
        // Get offline sales from IndexedDB
        const offlineSales = await getOfflineSales();
        
        if (offlineSales.length === 0) {
            console.log('[Service Worker] No offline sales to sync');
            return;
        }

        console.log(`[Service Worker] Syncing ${offlineSales.length} offline sales`);

        // Send each sale to server
        for (const sale of offlineSales) {
            try {
                const response = await fetch('/api/sales/sync/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(sale),
                });

                if (response.ok) {
                    // Remove from offline storage
                    await removeOfflineSale(sale.id);
                    console.log('[Service Worker] Sale synced:', sale.id);
                }
            } catch (error) {
                console.error('[Service Worker] Failed to sync sale:', error);
            }
        }

        // Notify all clients that sync is complete
        const clients = await self.clients.matchAll();
        clients.forEach((client) => {
            client.postMessage({
                type: 'SYNC_COMPLETE',
                count: offlineSales.length,
            });
        });
    } catch (error) {
        console.error('[Service Worker] Sync error:', error);
    }
}

// Helper functions for IndexedDB (simplified)
async function getOfflineSales() {
    // This would interact with IndexedDB
    // For now, return empty array
    return [];
}

async function removeOfflineSale(id) {
    // This would remove from IndexedDB
    console.log('[Service Worker] Removing offline sale:', id);
}

// Push notification support (for future use)
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Push received');
    
    const options = {
        body: event.data ? event.data.text() : 'New notification',
        icon: '/static/images/icon-192.png',
        badge: '/static/images/icon-192.png',
        vibrate: [200, 100, 200],
    };

    event.waitUntil(
        self.registration.showNotification('POS System', options)
    );
});
