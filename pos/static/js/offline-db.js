// IndexedDB Manager for Offline Data Storage
console.log('[OfflineDB] Script loaded');

class OfflineDB {
    constructor() {
        this.dbName = 'POSOfflineDB';
        this.version = 1;
        this.db = null;
    }

    // Initialize database
    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                console.log('[OfflineDB] Database initialized');
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Create object stores
                if (!db.objectStoreNames.contains('pending_sales')) {
                    const salesStore = db.createObjectStore('pending_sales', { keyPath: 'id' });
                    salesStore.createIndex('timestamp', 'timestamp', { unique: false });
                    salesStore.createIndex('status', 'status', { unique: false });
                }

                if (!db.objectStoreNames.contains('sync_log')) {
                    const logStore = db.createObjectStore('sync_log', { keyPath: 'id', autoIncrement: true });
                    logStore.createIndex('timestamp', 'timestamp', { unique: false });
                }

                console.log('[OfflineDB] Database schema created');
            };
        });
    }

    // Save pending sale
    async savePendingSale(saleData) {
        const sale = {
            id: `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            timestamp: Date.now(),
            status: 'pending',
            sync_attempts: 0,
            last_sync_attempt: null,
            error: null,
            data: saleData
        };

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const request = store.add(sale);

            request.onsuccess = () => {
                console.log('[OfflineDB] Sale saved:', sale.id);
                resolve(sale);
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Get all pending sales
    async getPendingSales() {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readonly');
            const store = transaction.objectStore('pending_sales');
            const index = store.index('status');
            const request = index.getAll('pending');

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    // Get pending sales count
    async getPendingCount() {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readonly');
            const store = transaction.objectStore('pending_sales');
            const index = store.index('status');
            const request = index.count('pending');

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    // Update sale status
    async updateSaleStatus(id, status, error = null) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const getRequest = store.get(id);

            getRequest.onsuccess = () => {
                const sale = getRequest.result;
                if (sale) {
                    sale.status = status;
                    sale.last_sync_attempt = Date.now();
                    sale.sync_attempts += 1;
                    if (error) {
                        sale.error = error;
                    }

                    const updateRequest = store.put(sale);
                    updateRequest.onsuccess = () => resolve(sale);
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    reject(new Error('Sale not found'));
                }
            };
            getRequest.onerror = () => reject(getRequest.error);
        });
    }

    // Delete synced sale
    async deleteSale(id) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const request = store.delete(id);

            request.onsuccess = () => {
                console.log('[OfflineDB] Sale deleted:', id);
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Log sync activity
    async logSync(action, details) {
        const logEntry = {
            timestamp: Date.now(),
            action: action,
            details: details
        };

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['sync_log'], 'readwrite');
            const store = transaction.objectStore('sync_log');
            const request = store.add(logEntry);

            request.onsuccess = () => resolve(logEntry);
            request.onerror = () => reject(request.error);
        });
    }

    // Get sync logs
    async getSyncLogs(limit = 50) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['sync_log'], 'readonly');
            const store = transaction.objectStore('sync_log');
            const index = store.index('timestamp');
            const request = index.openCursor(null, 'prev');
            const logs = [];

            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor && logs.length < limit) {
                    logs.push(cursor.value);
                    cursor.continue();
                } else {
                    resolve(logs);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Clear old synced data (cleanup)
    async cleanup(daysOld = 7) {
        const cutoffTime = Date.now() - (daysOld * 24 * 60 * 60 * 1000);

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const index = store.index('timestamp');
            const request = index.openCursor();
            let deletedCount = 0;

            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    const sale = cursor.value;
                    if (sale.status === 'synced' && sale.timestamp < cutoffTime) {
                        cursor.delete();
                        deletedCount++;
                    }
                    cursor.continue();
                } else {
                    console.log(`[OfflineDB] Cleanup: ${deletedCount} old records deleted`);
                    resolve(deletedCount);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }
}

// Export singleton instance
const offlineDB = new OfflineDB();
