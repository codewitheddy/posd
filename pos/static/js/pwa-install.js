// PWA Installation Handler
let deferredPrompt;
let installButton;

// Check if app is already installed
function isAppInstalled() {
    return window.matchMedia('(display-mode: standalone)').matches || 
           window.navigator.standalone === true;
}

// Show install prompt
window.addEventListener('beforeinstallprompt', (e) => {
    console.log('[PWA] Install prompt available');
    
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    
    // Stash the event so it can be triggered later
    deferredPrompt = e;
    
    // Show install button if not already installed
    if (!isAppInstalled()) {
        showInstallPromotion();
    }
});

// Show install promotion banner
function showInstallPromotion() {
    // Create install banner if it doesn't exist
    if (document.getElementById('pwa-install-banner')) {
        return;
    }

    const banner = document.createElement('div');
    banner.id = 'pwa-install-banner';
    banner.className = 'pwa-install-banner';
    banner.innerHTML = `
        <div class="pwa-install-content">
            <div class="pwa-install-icon">
                <i class="bi bi-download"></i>
            </div>
            <div class="pwa-install-text">
                <strong>Install POS App</strong>
                <p>Use offline & get faster access</p>
            </div>
            <div class="pwa-install-actions">
                <button id="pwa-install-btn" class="btn btn-sm btn-primary">
                    <i class="bi bi-plus-circle"></i> Install
                </button>
                <button id="pwa-dismiss-btn" class="btn btn-sm btn-outline-secondary">
                    <i class="bi bi-x"></i>
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(banner);

    // Add event listeners
    document.getElementById('pwa-install-btn').addEventListener('click', installApp);
    document.getElementById('pwa-dismiss-btn').addEventListener('click', dismissInstallPromotion);

    // Show banner with animation
    setTimeout(() => {
        banner.classList.add('show');
    }, 1000);
}

// Install the app
async function installApp() {
    if (!deferredPrompt) {
        console.log('[PWA] Install prompt not available');
        return;
    }

    // Show the install prompt
    deferredPrompt.prompt();

    // Wait for the user to respond to the prompt
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`[PWA] User response: ${outcome}`);

    if (outcome === 'accepted') {
        console.log('[PWA] App installed');
        dismissInstallPromotion();
    }

    // Clear the deferredPrompt
    deferredPrompt = null;
}

// Dismiss install promotion
function dismissInstallPromotion() {
    const banner = document.getElementById('pwa-install-banner');
    if (banner) {
        banner.classList.remove('show');
        setTimeout(() => {
            banner.remove();
        }, 300);
    }

    // Remember dismissal for 7 days
    localStorage.setItem('pwa-install-dismissed', Date.now());
}

// Check if should show install promotion
function shouldShowInstallPromotion() {
    const dismissed = localStorage.getItem('pwa-install-dismissed');
    if (!dismissed) return true;

    const dismissedTime = parseInt(dismissed);
    const sevenDays = 7 * 24 * 60 * 60 * 1000;
    
    return (Date.now() - dismissedTime) > sevenDays;
}

// Handle app installed event
window.addEventListener('appinstalled', () => {
    console.log('[PWA] App installed successfully');
    dismissInstallPromotion();
    
    // Show success message
    if (typeof showNotification === 'function') {
        showNotification('App installed! You can now use it offline.', 'success');
    }
});

// Register service worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker
            .register('/static/js/service-worker.js')
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
    // Show install promotion if appropriate
    if (!isAppInstalled() && shouldShowInstallPromotion() && deferredPrompt) {
        showInstallPromotion();
    }

    // Set initial connection status
    updateConnectionStatus(navigator.onLine);

    // Show installed indicator
    if (isAppInstalled()) {
        console.log('[PWA] Running as installed app');
        document.body.classList.add('pwa-installed');
    }
});
