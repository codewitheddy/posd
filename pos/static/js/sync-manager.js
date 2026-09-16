// Sync Manager for Offline Data Synchronization
console.log('[SyncManager] Script loaded');

class SyncManager {
    constructor() {
        this.isSyncing = false;
        this.syncInProgress = false;
        this.autoSyncEnabled = true;
        this.syncInterval = null;
        this.pingInterval = null;
        this.isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;
    }

    // Initialize sync manager
    async init() {
        console.log('[SyncManager] Initializing...');
        
        // Initialize offline database
        if (window.offlineDB) {
            await window.offlineDB.init();
        }
        
        // Update UI with pending count
        await this.updatePendingCount();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Setup auto-sync and connectivity heartbeats
        this.setupAutoSync();
        this.setupConnectivityCheck();
        
        // Service Worker message listener
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', (event) => {
                if (event.data && event.data.type === 'TRIGGER_SYNC_NOW') {
                    console.log('[SyncManager] SW triggered sync event received');
                    this.sync();
                }
            });
        }

        // Listen for locally saved offline sales
        window.addEventListener('offlinesale:saved', () => {
            this.updatePendingCount();
            if (this.isOnline && !this.syncInProgress) {
                // Opportunistic sync attempt
                setTimeout(() => this.sync(), 1500);
            }
        });
        
        console.log('[SyncManager] Initialized successfully');
    }

    // Setup event listeners
    setupEventListeners() {
        // Sync buttons click
        document.querySelectorAll('#syncButton, .btn-trigger-sync, [data-action="sync-now"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.manualSync();
            });
        });

        // Online/offline events
        window.addEventListener('online', () => this.onConnectionRestore());
        window.addEventListener('offline', () => this.onConnectionLost());
    }

    // Setup connectivity heartbeat pinging
    setupConnectivityCheck() {
        const checkPing = async () => {
            if (!navigator.onLine) {
                this.setConnectionState(false);
                return;
            }
            try {
                const res = await fetch('/ping/?_=' + Date.now(), { method: 'GET', cache: 'no-store' });
                this.setConnectionState(res.ok);
            } catch (err) {
                this.setConnectionState(false);
            }
        };

        this.pingInterval = setInterval(checkPing, 20000); // every 20s
        checkPing();
    }

    // Set connection state and notify UI
    setConnectionState(online) {
        const changed = this.isOnline !== online;
        this.isOnline = online;

        // Update indicator
        const el = document.getElementById('connection-status');
        if (el) {
            el.className = 'connection-status ' + (online ? 'online' : 'offline');
            el.innerHTML = online ? '<i class="bi bi-wifi"></i> Online' : '<i class="bi bi-wifi-off"></i> Offline Mode';
        }

        // Update all POS badges
        document.querySelectorAll('.pos-sync-status-badge').forEach(badge => {
            if (online) {
                badge.className = 'badge bg-success-subtle text-success border border-success-subtle pos-sync-status-badge';
                badge.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Online (Synced)';
            } else {
                badge.className = 'badge bg-warning-subtle text-warning border border-warning-subtle pos-sync-status-badge';
                badge.innerHTML = '<i class="bi bi-cloud-slash-fill me-1"></i> Offline Mode';
            }
        });

        if (changed) {
            window.dispatchEvent(new CustomEvent('connectivity:change', { detail: { online } }));
        }
    }

    // Setup auto-sync
    setupAutoSync() {
        this.syncInterval = setInterval(async () => {
            if (this.isOnline && this.autoSyncEnabled && !this.syncInProgress) {
                const count = await window.offlineDB.getPendingCount();
                if (count > 0) {
                    console.log('[SyncManager] Auto-sync triggered for', count, 'pending sales');
                    await this.sync();
                }
            }
        }, 30000); // 30 seconds
    }

    // Manual sync triggered by user
    async manualSync() {
        if (!this.isOnline) {
            this.showNotification('Cannot sync while offline. System will auto-sync when internet is back.', 'warning');
            return;
        }

        if (this.syncInProgress) {
            this.showNotification('Sync already in progress...', 'info');
            return;
        }

        const count = await window.offlineDB.getPendingCount();
        if (count === 0) {
            this.showNotification('All transactions are up to date. No pending offline sales.', 'info');
            return;
        }

        await this.sync();
    }

    // Main sync function (batches pending sales)
    async sync() {
        if (this.syncInProgress) {
            return;
        }

        if (!this.isOnline && !navigator.onLine) {
            return;
        }

        this.syncInProgress = true;
        this.showSyncProgress(true);

        try {
            const pendingRecords = await window.offlineDB.getPendingSales();
            if (!pendingRecords || pendingRecords.length === 0) {
                this.updatePendingCount();
                return;
            }

            console.log(`[SyncManager] Syncing ${pendingRecords.length} pending sales batch`);

            // Extract sales payload
            const salesPayload = pendingRecords.map(r => r.data || r);

            // Get CSRF Token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                              this.getCookie('csrftoken') || '';

            // Send batch to backend sync endpoint
            const response = await fetch('/api/sales/sync/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    sales: salesPayload
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `Server responded with ${response.status}`);
            }

            const result = await response.json();
            console.log('[SyncManager] Batch sync server response:', result);

            let successCount = 0;
            if (result.synced && Array.isArray(result.synced)) {
                for (const item of result.synced) {
                    const clientUuid = item.client_uuid;
                    // Find matching local record
                    const matching = pendingRecords.find(r => 
                        (r.data && (r.data.client_uuid === clientUuid || r.data.idempotency_key === clientUuid)) ||
                        r.idempotency_key === clientUuid || r.id === clientUuid
                    );
                    if (matching) {
                        await window.offlineDB.markSaleSynced(matching.id);
                        successCount++;
                    }
                }
            } else if (result.success) {
                // If synced without itemized breakdown, clean all
                for (const r of pendingRecords) {
                    await window.offlineDB.markSaleSynced(r.id);
                    successCount++;
                }
            }

            // Log sync result
            await window.offlineDB.logSync('batch_sync', {
                total: pendingRecords.length,
                synced: successCount,
                errors: result.errors || []
            });

            if (successCount > 0) {
                this.showNotification(`Successfully synchronized ${successCount} offline sale(s) to server!`, 'success');
            }

            // Update UI count
            await this.updatePendingCount();

        } catch (error) {
            console.warn('[SyncManager] Sync failed:', error);
            this.showNotification('Sync deferred: ' + error.message, 'warning');
        } finally {
            this.syncInProgress = false;
            this.showSyncProgress(false);
        }
    }

    // Connection restored
    async onConnectionRestore() {
        console.log('[SyncManager] Network online event received');
        this.setConnectionState(true);
        this.showNotification('Internet connection restored.', 'success');

        if (this.autoSyncEnabled) {
            const count = await window.offlineDB.getPendingCount();
            if (count > 0) {
                setTimeout(() => this.sync(), 1200);
            }
        }
    }

    // Connection lost
    onConnectionLost() {
        console.log('[SyncManager] Network offline event received');
        this.setConnectionState(false);
        this.showNotification('Internet disconnected. Working in Offline Mode — sales will be saved locally.', 'warning');
    }

    // Update pending count badge
    async updatePendingCount() {
        if (!window.offlineDB) return;
        const count = await window.offlineDB.getPendingCount();

        document.querySelectorAll('#pendingCount, .pending-sync-count').forEach(badge => {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'inline-block' : 'none';
        });

        document.querySelectorAll('#syncButton, .btn-trigger-sync').forEach(syncButton => {
            if (count > 0) {
                syncButton.classList.add('btn-warning');
                syncButton.classList.remove('btn-secondary', 'btn-outline-secondary');
                syncButton.title = `${count} pending sale(s) waiting to sync`;
            } else {
                syncButton.classList.remove('btn-warning');
                syncButton.classList.add('btn-outline-secondary');
                syncButton.title = 'No pending sales to sync';
            }
        });

        // Broadcast count update
        window.dispatchEvent(new CustomEvent('sync:pending-count', { detail: { count } }));
    }

    // Show sync progress spinner / modal
    showSyncProgress(show) {
        document.querySelectorAll('.sync-spinner').forEach(s => {
            s.style.display = show ? 'inline-block' : 'none';
        });
    }

    // Helper: Show toast notification
    showNotification(message, type = 'info') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            console.log(`[Notification ${type}]: ${message}`);
        }
    }

    // Helper: Cookie extraction
    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// Create singleton instance
const syncManager = new SyncManager();

if (typeof window !== 'undefined') {
    window.syncManager = syncManager;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            syncManager.init().catch(err => console.error('[SyncManager] Init failed:', err));
        });
    } else {
        syncManager.init().catch(err => console.error('[SyncManager] Init failed:', err));
    }
}
