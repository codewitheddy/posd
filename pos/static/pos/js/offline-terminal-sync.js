/**
 * Offline-Resilient POS Terminal Synchronization Engine
 * 
 * Features:
 * - Local Outbox Queue in IndexedDB (stamped with client-side UUID idempotency keys)
 * - Read-only local cache for catalog, prices, and stock levels (display only)
 * - Opportunistic background sync loop (15-30s intervals)
 * - Immediate sync on network reconnect ('online' event)
 * - Exponential backoff on connection errors
 * - Single-round-trip batched synchronization with server
 */

class POSTerminalSyncEngine {
    constructor(options = {}) {
        this.dbName = options.dbName || 'MaridPOSTerminalDB';
        this.dbVersion = options.dbVersion || 2;
        this.apiBaseUrl = options.apiBaseUrl || '/api/terminals/sync/';
        this.terminalToken = options.terminalToken || localStorage.getItem('pos_terminal_token') || '';
        this.terminalId = options.terminalId || localStorage.getItem('pos_terminal_id') || null;
        
        // Polling & backoff settings
        this.minIntervalMs = options.minIntervalMs || 15000;  // 15s
        this.maxIntervalMs = options.maxIntervalMs || 120000; // 2 min max
        this.currentIntervalMs = this.minIntervalMs;
        this.syncInProgress = false;
        this.syncTimer = null;
        this.db = null;
        
        // Event listeners & status
        this.lastSyncTimestamp = null;
        this.onSyncStatusChange = options.onSyncStatusChange || null;
    }

    /**
     * Initialize IndexedDB and start background sync workers
     */
    async init() {
        await this.initDatabase();
        await this.loadMetadata();
        this.setupNetworkListeners();
        this.startBackgroundLoop();
        console.log('[POSTerminalSync] Initialized. Terminal ID:', this.terminalId);
        
        // Initial sync attempt if online
        if (navigator.onLine) {
            this.syncNow();
        }
    }

    /**
     * Initialize IndexedDB Schema
     */
    initDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);

            request.onerror = () => {
                console.error('[POSTerminalSync] IndexedDB error:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                this.db = request.result;
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // 1. Outbox Sales Store (stores local sales waiting for sync)
                if (!db.objectStoreNames.contains('outbox_sales')) {
                    const outboxStore = db.createObjectStore('outbox_sales', { keyPath: 'idempotency_key' });
                    outboxStore.createIndex('sync_status', 'sync_status', { unique: false });
                    outboxStore.createIndex('client_created_at', 'client_created_at', { unique: false });
                }

                // 2. Catalog Cache (Products, Categories, VAT codes, Payment Methods)
                if (!db.objectStoreNames.contains('catalog_products')) {
                    const prodStore = db.createObjectStore('catalog_products', { keyPath: 'id' });
                    prodStore.createIndex('barcode', 'barcode', { unique: false });
                    prodStore.createIndex('product_code', 'product_code', { unique: false });
                    prodStore.createIndex('category_id', 'category_id', { unique: false });
                }

                if (!db.objectStoreNames.contains('catalog_categories')) {
                    db.createObjectStore('catalog_categories', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('catalog_vat_codes')) {
                    db.createObjectStore('catalog_vat_codes', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('catalog_payment_methods')) {
                    db.createObjectStore('catalog_payment_methods', { keyPath: 'id' });
                }

                // 3. Branch Stock Levels (Display only)
                if (!db.objectStoreNames.contains('branch_stock_levels')) {
                    db.createObjectStore('branch_stock_levels', { keyPath: 'product_id' });
                }

                // 4. Distribution Status Cache (Requisitions, Transfers, Dispatches)
                if (!db.objectStoreNames.contains('distribution_requisitions')) {
                    db.createObjectStore('distribution_requisitions', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('distribution_transfers')) {
                    db.createObjectStore('distribution_transfers', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('distribution_dispatches')) {
                    db.createObjectStore('distribution_dispatches', { keyPath: 'id' });
                }

                // 5. Metadata Store
                if (!db.objectStoreNames.contains('sync_meta')) {
                    db.createObjectStore('sync_meta', { keyPath: 'key' });
                }
            };
        });
    }

    /**
     * Generate UUID v4 for client-side idempotency stamping
     */
    generateUUID() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    /**
     * Record a new Sale locally in the Outbox.
     * Stamped immediately with a client UUID idempotency key.
     */
    async recordSaleLocally(saleData) {
        if (!saleData.idempotency_key) {
            saleData.idempotency_key = this.generateUUID();
        }
        if (!saleData.client_created_at) {
            saleData.client_created_at = new Date().toISOString();
        }
        saleData.sync_status = 'pending';
        saleData.retry_count = 0;

        await this.putRecord('outbox_sales', saleData);
        console.log('[POSTerminalSync] Recorded local sale with idempotency key:', saleData.idempotency_key);

        this.notifyStatusChange('sale_queued', { sale: saleData });

        // Trigger opportunistic sync if online
        if (navigator.onLine && !this.syncInProgress) {
            this.syncNow();
        }

        return saleData;
    }

    /**
     * Get all pending unsynced sales from outbox
     */
    async getPendingOutboxSales() {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['outbox_sales'], 'readonly');
            const store = transaction.objectStore('outbox_sales');
            const request = store.getAll();

            request.onsuccess = () => {
                const all = request.result || [];
                const pending = all.filter(s => s.sync_status !== 'synced');
                resolve(pending);
            };
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Setup online/offline network listeners
     */
    setupNetworkListeners() {
        window.addEventListener('online', () => {
            console.log('[POSTerminalSync] Network online event received. Triggering immediate sync.');
            this.currentIntervalMs = this.minIntervalMs;
            this.notifyStatusChange('online');
            this.syncNow();
            this.startBackgroundLoop();
        });

        window.addEventListener('offline', () => {
            console.log('[POSTerminalSync] Network offline event received.');
            this.notifyStatusChange('offline');
        });
    }

    /**
     * Start background polling worker
     */
    startBackgroundLoop() {
        if (this.syncTimer) {
            clearTimeout(this.syncTimer);
        }

        const scheduleNext = () => {
            this.syncTimer = setTimeout(async () => {
                if (navigator.onLine && !this.syncInProgress) {
                    await this.syncNow();
                }
                scheduleNext();
            }, this.currentIntervalMs);
        };

        scheduleNext();
    }

    /**
     * Execute a full single-round-trip synchronization
     */
    async syncNow() {
        if (this.syncInProgress) {
            return;
        }

        if (!navigator.onLine) {
            this.notifyStatusChange('offline');
            return;
        }

        this.syncInProgress = true;
        this.notifyStatusChange('syncing');

        try {
            const pendingSales = await this.getPendingOutboxSales();
            const lastSync = await this.getMeta('last_sync_timestamp');

            const payload = {
                since_timestamp: lastSync || null,
                outbox: pendingSales
            };

            const url = this.terminalId ? `/api/terminals/${this.terminalId}/sync/` : this.apiBaseUrl;
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            };

            if (this.terminalToken) {
                headers['X-Terminal-Token'] = this.terminalToken;
                headers['Authorization'] = `Terminal ${this.terminalToken}`;
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errText}`);
            }

            const data = await response.json();
            await this.applySyncResponse(data, pendingSales);

            // Reset backoff on success
            this.currentIntervalMs = this.minIntervalMs;
            this.notifyStatusChange('synced', { data });

        } catch (error) {
            console.warn('[POSTerminalSync] Sync failed:', error.message);
            // Apply exponential backoff
            this.currentIntervalMs = Math.min(this.currentIntervalMs * 1.5, this.maxIntervalMs);
            this.notifyStatusChange('error', { error: error.message });
        } finally {
            this.syncInProgress = false;
        }
    }

    /**
     * Ingest server response into local IndexedDB
     */
    async applySyncResponse(data, sentSales) {
        const tx = this.db.transaction([
            'outbox_sales', 'catalog_products', 'catalog_categories',
            'catalog_vat_codes', 'catalog_payment_methods', 'branch_stock_levels',
            'distribution_requisitions', 'distribution_transfers', 'distribution_dispatches',
            'sync_meta'
        ], 'readwrite');

        // 1. Mark synced sales / remove synced outbox items
        const outboxStore = tx.objectStore('outbox_sales');
        if (data.processed_sales && data.processed_sales.length > 0) {
            for (const item of data.processed_sales) {
                if (item.idempotency_key && (item.status === 'processed' || item.status === 'already_processed')) {
                    outboxStore.delete(item.idempotency_key);
                }
            }
        }

        // 2. Cache catalog updates
        if (data.catalog_updates) {
            const { products, categories, vat_codes, payment_methods } = data.catalog_updates;
            if (products && products.length > 0) {
                const prodStore = tx.objectStore('catalog_products');
                for (const p of products) {
                    prodStore.put(p);
                }
            }
            if (categories && categories.length > 0) {
                const catStore = tx.objectStore('catalog_categories');
                for (const c of categories) {
                    catStore.put(c);
                }
            }
            if (vat_codes && vat_codes.length > 0) {
                const vatStore = tx.objectStore('catalog_vat_codes');
                for (const v of vat_codes) {
                    vatStore.put(v);
                }
            }
            if (payment_methods && payment_methods.length > 0) {
                const pmStore = tx.objectStore('catalog_payment_methods');
                for (const pm of payment_methods) {
                    pmStore.put(pm);
                }
            }
        }

        // 3. Cache Branch Stock Display Levels
        if (data.branch_stock_levels && data.branch_stock_levels.length > 0) {
            const stockStore = tx.objectStore('branch_stock_levels');
            for (const st of data.branch_stock_levels) {
                stockStore.put(st);
            }
        }

        // 4. Cache Branch Distribution Updates
        if (data.distribution_updates) {
            const { requisitions, transfers, dispatches } = data.distribution_updates;
            if (requisitions && requisitions.length > 0) {
                const reqStore = tx.objectStore('distribution_requisitions');
                for (const r of requisitions) {
                    reqStore.put(r);
                }
            }
            if (transfers && transfers.length > 0) {
                const trfStore = tx.objectStore('distribution_transfers');
                for (const t of transfers) {
                    trfStore.put(t);
                }
            }
            if (dispatches && dispatches.length > 0) {
                const dspStore = tx.objectStore('distribution_dispatches');
                for (const d of dispatches) {
                    dspStore.put(d);
                }
            }
        }

        // 5. Update Metadata
        const metaStore = tx.objectStore('sync_meta');
        if (data.server_timestamp) {
            metaStore.put({ key: 'last_sync_timestamp', value: data.server_timestamp });
            this.lastSyncTimestamp = data.server_timestamp;
        }

        return new Promise((resolve, reject) => {
            tx.oncomplete = () => {
                console.log('[POSTerminalSync] Sync transaction committed successfully.');
                // Dispatch event to window
                window.dispatchEvent(new CustomEvent('pos:sync:completed', { detail: data }));
                resolve();
            };
            tx.onerror = () => reject(tx.error);
        });
    }

    /**
     * Put record helper
     */
    putRecord(storeName, record) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([storeName], 'readwrite');
            const store = tx.objectStore(storeName);
            const req = store.put(record);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * Get metadata value
     */
    getMeta(key) {
        return new Promise((resolve) => {
            if (!this.db) return resolve(null);
            const tx = this.db.transaction(['sync_meta'], 'readonly');
            const store = tx.objectStore('sync_meta');
            const req = store.get(key);
            req.onsuccess = () => resolve(req.result ? req.result.value : null);
            req.onerror = () => resolve(null);
        });
    }

    /**
     * Load initial metadata
     */
    async loadMetadata() {
        this.lastSyncTimestamp = await this.getMeta('last_sync_timestamp');
    }

    /**
     * Notify listeners of sync status changes
     */
    notifyStatusChange(status, extra = {}) {
        if (typeof this.onSyncStatusChange === 'function') {
            this.onSyncStatusChange(status, extra);
        }
        window.dispatchEvent(new CustomEvent('pos:sync:status', {
            detail: { status, timestamp: new Date().toISOString(), ...extra }
        }));
    }
}

// Global instance for browser POS
window.POSTerminalSync = POSTerminalSyncEngine;
