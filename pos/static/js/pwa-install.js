// PWA Service Worker Handler (Install prompts removed)

// Register service worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker
            .register('/sw.js')
            .then((registration) => {
                console.log('[PWA] Service Worker registered:', registration.scope);

                // Check for updates periodically
                setInterval(() => {
                    registration.update();
                }, 60000); // Check every minute
            })
            .catch((error) => {
                console.error('[PWA] Service Worker registration failed:', error);
            });

        // Listen for service worker messages
        navigator.serviceWorker.addEventListener('message', (event) => {
            console.log('[PWA] Message from SW:', event.data);

            if (event.data.type === 'SYNC_COMPLETE') {
                if (typeof showNotification === 'function') {
                    showNotification(
                        `${event.data.count} offline sale(s) synced successfully!`,
                        'success'
                    );
                }
            }
        });
    });
}

// Monitor online/offline status
window.addEventListener('online', () => {
    console.log('[PWA] Back online');
    updateConnectionStatus(true);
    
    // Trigger background sync if available
    if ('serviceWorker' in navigator && 'sync' in ServiceWorkerRegistration.prototype) {
        navigator.serviceWorker.ready.then((registration) => {
            return registration.sync.register('sync-sales');
        });
    }
});

window.addEventListener('offline', () => {
    console.log('[PWA] Gone offline');
    updateConnectionStatus(false);
});

// Update connection status indicator
function updateConnectionStatus(isOnline) {
    const statusEl = document.getElementById('connection-status');
    if (statusEl) {
        if (isOnline) {
            statusEl.className = 'connection-status online';
            statusEl.innerHTML = '<i class="bi bi-wifi"></i> Online';
        } else {
            statusEl.className = 'connection-status offline';
            statusEl.innerHTML = '<i class="bi bi-wifi-off"></i> Offline';
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Set initial connection status
    updateConnectionStatus(navigator.onLine);
});
