/**
 * Service Worker for Offline-First POS System
 * Handles caching, offline detection, and background sync
 */

const CACHE_VERSION = 'pos-v1';
const CACHE_STATIC = `${CACHE_VERSION}-static`;
const CACHE_DYNAMIC = `${CACHE_VERSION}-dynamic`;
const CACHE_API = `${CACHE_VERSION}-api`;

// Files to cache immediately on install
const STATIC_ASSETS = [
    '/',
    '/static/pos/css/style.css',
    '/static/pos/js/app.js',
    '/static/pos/js/offline-db.js',
    '/static/pos/js/sync-manager.js',
    '/offline.html',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing service worker...');
    
    event.waitUntil(
        caches.open(CACHE_STATIC)
            .then((cache) => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating service worker...');
    
    event.waitUntil(
        caches.keys()
            .then((keys) => {
                return Promise.all(
                    keys
                        .filter((key) => key.startsWith('pos-') && key !== CACHE_STATIC && key !== CACHE_DYNAMIC && key !== CACHE_API)
                        .map((key) => caches.delete(key))
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch event - network first, fallback to cache
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // API requests - network first with cache fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(networkFirstStrategy(request, CACHE_API));
        return;
    }
    
    // Static assets - cache first
    if (request.destination === 'style' || request.destination === 'script' || request.destination === 'image') {
        event.respondWith(cacheFirstStrategy(request, CACHE_STATIC));
        return;
    }
    
    // HTML pages - network first
    if (request.destination === 'document') {
        event.respondWith(networkFirstStrategy(request, CACHE_DYNAMIC));
        return;
    }
    
    // Default - network first
    event.respondWith(networkFirstStrategy(request, CACHE_DYNAMIC));
});

// Network first strategy - try network, fallback to cache
async function networkFirstStrategy(request, cacheName) {
    try {
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('[SW] Network failed, trying cache:', request.url);
        
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline page for navigation requests
        if (request.destination === 'document') {
            return caches.match('/offline.html');
        }
        
        // Return error response
        return new Response('Offline - resource not available', {
            status: 503,
            statusText: 'Service Unavailable',
            headers: new Headers({
                'Content-Type': 'text/plain'
            })
        });
    }
}

// Cache first strategy - try cache, fallback to network
async function cacheFirstStrategy(request, cacheName) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('[SW] Failed to fetch:', request.url);
        return new Response('Resource not available', {
            status: 404,
            statusText: 'Not Found'
        });
    }
}

// Background sync event - sync queued data when online
self.addEventListener('sync', (event) => {
    console.log('[SW] Background sync triggered:', event.tag);
    
    if (event.tag === 'sync-sales') {
        event.waitUntil(syncSales());
    } else if (event.tag === 'sync-all') {
        event.waitUntil(syncAll());
    }
});

// Sync sales to server
async function syncSales() {
    try {
        // This will be implemented in sync-manager.js
        const response = await fetch('/api/v1/sync/push/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                device_id: await getDeviceId(),
                changes: await getPendingChanges()
            })
        });
        
        if (response.ok) {
            console.log('[SW] Sync successful');
            await clearPendingChanges();
        } else {
            console.error('[SW] Sync failed:', response.status);
        }
    } catch (error) {
        console.error('[SW] Sync error:', error);
        throw error; // Retry sync
    }
}

// Sync all data
async function syncAll() {
    await syncSales();
    // Add other sync operations here
}

// Helper functions (will be implemented in IndexedDB)
async function getDeviceId() {
    return 'device-' + Math.random().toString(36).substr(2, 9);
}

async function getPendingChanges() {
    return { sales: [] }; // Placeholder
}

async function clearPendingChanges() {
    // Placeholder
}

// Message event - handle messages from clients
self.addEventListener('message', (event) => {
    console.log('[SW] Message received:', event.data);
    
    if (event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    } else if (event.data.type === 'SYNC_NOW') {
        self.registration.sync.register('sync-all');
    }
});
