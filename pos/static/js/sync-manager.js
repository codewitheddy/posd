// Sync Manager for Offline Data Synchronization
console.log('[SyncManager] Script loaded');

class SyncManager {
    constructor() {
        this.isSyncing = false;
        this.syncInProgress = false;
        this.autoSyncEnabled = true;
        this.syncInterval = null;
    }

    // Initialize sync manager
    async init() {
        console.log('[SyncManager] Initializing...');
        
        // Initialize offline database
        await offlineDB.init();
        
        // Update UI with pending count
        await this.updatePendingCount();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Setup auto-sync on connection restore
        this.setupAutoSync();
        
        // Periodic cleanup
        this.setupCleanup();
        
        console.log('[SyncManager] Initialized');
    }

    // Setup event listeners
    setupEventListeners() {
        // Sync button click
        const syncButton = document.getElementById('syncButton');
        if (syncButton) {
            syncButton.addEventListener('click', () => this.manualSync());
            console.log('[SyncManager] Sync button event listener attached');
        } else {
            console.warn('[SyncManager] Sync button not found in DOM');
        }

        // Online/offline events
        window.addEventListener('online', () => this.onConnectionRestore());
        window.addEventListener('offline', () => this.onConnectionLost());
        console.log('[SyncManager] Online/offline event listeners attached');
    }

    // Setup auto-sync
    setupAutoSync() {
        // Check for pending items every 30 seconds when online
        this.syncInterval = setInterval(async () => {
            if (navigator.onLine && this.autoSyncEnabled && !this.syncInProgress) {
                const count = await offlineDB.getPendingCount();
                if (count > 0) {
                    console.log('[SyncManager] Auto-sync triggered');
                    await this.sync();
                }
            }
        }, 30000); // 30 seconds
    }

    // Setup periodic cleanup
    setupCleanup() {
        // Cleanup old data once per day
        setInterval(async () => {
            await offlineDB.cleanup(7); // Delete synced items older than 7 days
        }, 24 * 60 * 60 * 1000); // 24 hours
    }

    // Manual sync triggered by user
    async manualSync() {
        if (!navigator.onLine) {
            this.showNotification('Cannot sync while offline', 'warning');
            return;
        }

        if (this.syncInProgress) {
            this.showNotification('Sync already in progress', 'info');
            return;
        }

        const count = await offlineDB.getPendingCount();
        if (count === 0) {
            this.showNotification('No pending data to sync', 'info');
            return;
        }

        // Show confirmation
        if (!confirm(`Sync ${count} pending sale(s) to server?`)) {
            return;
        }

        await this.sync();
    }

    // Main sync function
    async sync() {
        if (this.syncInProgress) {
            console.log('[SyncManager] Sync already in progress');
            return;
        }

        this.syncInProgress = true;
        this.showSyncProgress(true);

        try {
            const pendingSales = await offlineDB.getPendingSales();
            console.log(`[SyncManager] Syncing ${pendingSales.length} sales`);

            let successCount = 0;
            let failCount = 0;

            for (let i = 0; i < pendingSales.length; i++) {
                const sale = pendingSales[i];
                this.updateSyncProgress(i + 1, pendingSales.length);

                try {
                    await this.syncSale(sale);
                    successCount++;
                } catch (error) {
                    console.error('[SyncManager] Failed to sync sale:', sale.id, error);
                    failCount++;
                }
            }

            // Log sync result
            await offlineDB.logSync('manual_sync', {
                total: pendingSales.length,
                success: successCount,
                failed: failCount
            });

            // Show result
            if (failCount === 0) {
                this.showNotification(`Successfully synced ${successCount} sale(s)`, 'success');
            } else {
                this.showNotification(
                    `Synced ${successCount} sale(s), ${failCount} failed`,
                    'warning'
                );
            }

            // Update pending count
            await this.updatePendingCount();

        } catch (error) {
            console.error('[SyncManager] Sync error:', error);
            this.showNotification('Sync failed: ' + error.message, 'danger');
        } finally {
            this.syncInProgress = false;
            this.showSyncProgress(false);
        }
    }

    // Sync individual sale
    async syncSale(sale) {
        try {
            // Update status to syncing
            await offlineDB.updateSaleStatus(sale.id, 'syncing');

            // Get CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

            // Send to server
            const response = await fetch('/api/sales/sync/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    temp_id: sale.id,
                    sale_data: sale.data
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Sync failed');
            }

            const result = await response.json();

            // Mark as synced and delete
            await offlineDB.updateSaleStatus(sale.id, 'synced');
            await offlineDB.deleteSale(sale.id);

            console.log('[SyncManager] Sale synced successfully:', sale.id, '→', result.sale_id);
            return result;

        } catch (error) {
            // Mark as failed
            await offlineDB.updateSaleStatus(sale.id, 'failed', error.message);
            throw error;
        }
    }

    // Connection restored
    async onConnectionRestore() {
        console.log('[SyncManager] Connection restored');
        this.showNotification('Connection restored', 'success');

        // Auto-sync if enabled
        if (this.autoSyncEnabled) {
            const count = await offlineDB.getPendingCount();
            if (count > 0) {
                setTimeout(() => this.sync(), 2000); // Wait 2 seconds then sync
            }
        }
    }

    // Connection lost
    onConnectionLost() {
        console.log('[SyncManager] Connection lost');
        this.showNotification('Working offline - sales will be synced later', 'warning');
    }

    // Update pending count badge
    async updatePendingCount() {
        const count = await offlineDB.getPendingCount();
        const badge = document.getElementById('pendingCount');
        const syncButton = document.getElementById('syncButton');

        if (badge) {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'inline-block' : 'none';
        }

        if (syncButton) {
            syncButton.disabled = count === 0 || !navigator.onLine;
            if (count > 0) {
                syncButton.classList.add('btn-warning');
                syncButton.classList.remove('btn-secondary');
            } else {
                syncButton.classList.add('btn-secondary');
                syncButton.classList.remove('btn-warning');
            }
        }
    }

    // Show sync progress modal
    showSyncProgress(show) {
        let modal = document.getElementById('syncProgressModal');
        
        if (show && !modal) {
            // Create modal
            modal = document.createElement('div');
            modal.id = 'syncProgressModal';
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-sync fa-spin"></i> Syncing Data
                            </h5>
                        </div>
                        <div class="modal-body">
                            <div class="progress mb-3" style="height: 25px;">
                                <div id="syncProgressBar" class="progress-bar progress-bar-striped progress-bar-animated" 
                                     role="progressbar" style="width: 0%">
                                    <span id="syncProgressText">0/0</span>
                                </div>
                            </div>
                            <p class="text-center text-muted mb-0">
                                <small>Please wait while we upload your sales...</small>
                            </p>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        if (modal) {
            if (show) {
                $(modal).modal('show');
            } else {
                $(modal).modal('hide');
            }
        }
    }

    // Update sync progress
    updateSyncProgress(current, total) {
        const progressBar = document.getElementById('syncProgressBar');
        const progressText = document.getElementById('syncProgressText');

        if (progressBar && progressText) {
            const percentage = (current / total) * 100;
            progressBar.style.width = percentage + '%';
            progressText.textContent = `${current}/${total}`;
        }
    }

    // Show notification
    showNotification(message, type = 'info') {
        // Check if body exists
        if (!document.body) {
            console.warn('[SyncManager] Cannot show notification - document.body not ready');
            return;
        }
        
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        toast.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px;';
        toast.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 5000);
    }
}

// Export singleton instance
const syncManager = new SyncManager();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[SyncManager] DOM loaded, initializing...');
        syncManager.init().catch(err => {
            console.error('[SyncManager] Initialization failed:', err);
        });
    });
} else {
    console.log('[SyncManager] DOM already loaded, initializing...');
    syncManager.init().catch(err => {
        console.error('[SyncManager] Initialization failed:', err);
    });
}
