/**
 * Sync Manager for Offline-First POS
 * Handles bidirectional sync between local IndexedDB and server
 */

class SyncManager {
    constructor() {
        this.apiBase = '/api/v1';
        this.syncInProgress = false;
        this.syncInterval = null;
        this.autoSyncEnabled = true;
        this.autoSyncIntervalMs = 60000; // 1 minute
    }

    /**
     * Initialize sync manager
     */
    async init() {
        await offlineDB.init();
        
        // Start auto-sync if online
        if (navigator.onLine) {
            this.startAutoSync();
        }

        // Listen for online/offline events
        window.addEventListener('online', () => {
            console.log('[Sync] Back online - starting sync');
            this.syncNow();
            this.startAutoSync();
        });

        window.addEventListener('offline', () => {
            console.log('[Sync] Gone offline - stopping auto-sync');
            this.stopAutoSync();
        });

        // Register service worker for background sync
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            const registration = await navigator.serviceWorker.ready;
            console.log('[Sync] Background sync available');
        }
    }

    /**
     * Start automatic sync
     */
    startAutoSync() {
        if (this.syncInterval) return;
        
        this.syncInterval = setInterval(() => {
            if (this.autoSyncEnabled && navigator.onLine) {
                this.syncNow();
            }
        }, this.autoSyncIntervalMs);
        
        console.log('[Sync] Auto-sync started');
    }

    /**
     * Stop automatic sync
     */
    stopAutoSync() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
            console.log('[Sync] Auto-sync stopped');
        }
    }

    /**
     * Perform full sync now
     */
    async syncNow() {
        if (this.syncInProgress) {
            console.log('[Sync] Sync already in progress');
            return;
        }

        if (!navigator.onLine) {
            console.log('[Sync] Cannot sync - offline');
            return;
        }

        this.syncInProgress = true;
        this.updateSyncStatus('syncing');

        try {
            // Push local changes first
            await this.pushChanges();
            
            // Then pull server updates
            await this.pullUpdates();
            
            console.log('[Sync] Sync completed successfully');
            this.updateSyncStatus('synced');
        } catch (error) {
            console.error('[Sync] Sync failed:', error);
            this.updateSyncStatus('error');
        } finally {
            this.syncInProgress = false;
        }
    }

    /**
     * Push local changes to server
     */
    async pushChanges() {
        console.log('[Sync] Pushing local changes...');
        
        const deviceId = await offlineDB.getDeviceId();
        const unsyncedSales = await offlineDB.getUnsyncedSales();
        const syncQueue = await offlineDB.getSyncQueue();

        if (unsyncedSales.length === 0 && syncQueue.length === 0) {
            console.log('[Sync] No changes to push');
            return;
        }

        const changes = {
            sales: unsyncedSales,
            queue: syncQueue
        };

        const response = await this.apiRequest('/sync/push/', {
            method: 'POST',
            body: JSON.stringify({
                device_id: deviceId,
                changes: changes
            })
        });

        if (response.ok) {
            const result = await response.json();
            
            // Mark synced sales
            for (const sale of unsyncedSales) {
                await offlineDB.markSaleSynced(sale.id);
            }
            
            // Clear sync queue
            await offlineDB.clearSyncQueue();
            
            console.log('[Sync] Push completed:', result);
        } else {
            throw new Error(`Push failed: ${response.status}`);
        }
    }

    /**
     * Pull updates from server
     */
    async pullUpdates() {
        console.log('[Sync] Pulling server updates...');
        
        const deviceId = await offlineDB.getDeviceId();
        const lastSync = await offlineDB.getLastSync();

        const response = await this.apiRequest('/sync/pull/', {
            method: 'POST',
            body: JSON.stringify({
                device_id: deviceId,
                last_sync: lastSync,
                models: ['products', 'categories', 'customers', 'suppliers', 'payment_methods']
            })
        });

        if (response.ok) {
            const data = await response.json();
            
            // Update local database
            if (data.products && data.products.length > 0) {
                await offlineDB.putBulk('products', data.products);
                console.log(`[Sync] Updated ${data.products.length} products`);
            }
            
            if (data.categories && data.categories.length > 0) {
                await offlineDB.putBulk('categories', data.categories);
                console.log(`[Sync] Updated ${data.categories.length} categories`);
            }
            
            if (data.customers && data.customers.length > 0) {
                await offlineDB.putBulk('customers', data.customers);
                console.log(`[Sync] Updated ${data.customers.length} customers`);
            }
            
            if (data.suppliers && data.suppliers.length > 0) {
                await offlineDB.putBulk('suppliers', data.suppliers);
                console.log(`[Sync] Updated ${data.suppliers.length} suppliers`);
            }
            
            if (data.payment_methods && data.payment_methods.length > 0) {
                await offlineDB.putBulk('payment_methods', data.payment_methods);
                console.log(`[Sync] Updated ${data.payment_methods.length} payment methods`);
            }
            
            // Update last sync timestamp
            await offlineDB.setLastSync(data.timestamp);
            
            console.log('[Sync] Pull completed');
        } else {
            throw new Error(`Pull failed: ${response.status}`);
        }
    }

    /**
     * Make API request with authentication
     */
    async apiRequest(endpoint, options = {}) {
        const token = localStorage.getItem('auth_token');
        
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': token ? `Bearer ${token}` : ''
            }
        };

        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        };

        return fetch(this.apiBase + endpoint, mergedOptions);
    }

    /**
     * Update sync status in UI
     */
    updateSyncStatus(status) {
        const event = new CustomEvent('syncstatus', {
            detail: { status }
        });
        window.dispatchEvent(event);
    }

    /**
     * Get sync statistics
     */
    async getSyncStats() {
        const unsyncedSales = await offlineDB.getUnsyncedSales();
        const syncQueue = await offlineDB.getSyncQueue();
        const lastSync = await offlineDB.getLastSync();

        return {
            unsyncedSales: unsyncedSales.length,
            queuedChanges: syncQueue.length,
            lastSync: lastSync,
            isOnline: navigator.onLine,
            syncInProgress: this.syncInProgress
        };
    }

    /**
     * Force background sync (if supported)
     */
    async requestBackgroundSync() {
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('sync-all');
                console.log('[Sync] Background sync registered');
            } catch (error) {
                console.error('[Sync] Background sync failed:', error);
            }
        }
    }
}

// Export singleton instance
const syncManager = new SyncManager();

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => syncManager.init());
} else {
    syncManager.init();
}
