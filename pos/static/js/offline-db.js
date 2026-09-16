// IndexedDB Manager for Offline Data Storage & Catalog Caching
console.log('[OfflineDB] Script loaded');

class OfflineDB {
    constructor() {
        this.dbName = 'POSOfflineDB';
        this.version = 2;
        this.db = null;
        this.isPersistent = false;
    }

    // Initialize database and request storage persistence
    async init() {
        await this.requestStoragePersistence();

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onerror = () => {
                console.error('[OfflineDB] Initialization error:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                this.db = request.result;
                console.log('[OfflineDB] Database initialized successfully (v' + this.version + ')');
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                console.log('[OfflineDB] Upgrading database schema to v' + event.newVersion);

                // 1. Pending Sales Outbox Store
                if (!db.objectStoreNames.contains('pending_sales')) {
                    const salesStore = db.createObjectStore('pending_sales', { keyPath: 'id' });
                    salesStore.createIndex('timestamp', 'timestamp', { unique: false });
                    salesStore.createIndex('status', 'status', { unique: false });
                    salesStore.createIndex('idempotency_key', 'idempotency_key', { unique: false });
                }

                // 2. Cached Products Catalog Store
                if (!db.objectStoreNames.contains('cached_products')) {
                    const prodStore = db.createObjectStore('cached_products', { keyPath: 'id' });
                    prodStore.createIndex('barcode', 'barcode', { unique: false });
                    prodStore.createIndex('product_code', 'product_code', { unique: false });
                    prodStore.createIndex('name', 'name', { unique: false });
                    prodStore.createIndex('category_id', 'category_id', { unique: false });
                }

                // 3. Cached Categories
                if (!db.objectStoreNames.contains('cached_categories')) {
                    db.createObjectStore('cached_categories', { keyPath: 'id' });
                }

                // 4. Cached Customers
                if (!db.objectStoreNames.contains('cached_customers')) {
                    const custStore = db.createObjectStore('cached_customers', { keyPath: 'id' });
                    custStore.createIndex('phone', 'phone', { unique: false });
                    custStore.createIndex('name', 'name', { unique: false });
                }

                // 5. Cached Payment Methods
                if (!db.objectStoreNames.contains('cached_payment_methods')) {
                    db.createObjectStore('cached_payment_methods', { keyPath: 'id' });
                }

                // 6. Sync Log & Metadata
                if (!db.objectStoreNames.contains('sync_log')) {
                    const logStore = db.createObjectStore('sync_log', { keyPath: 'id', autoIncrement: true });
                    logStore.createIndex('timestamp', 'timestamp', { unique: false });
                }

                if (!db.objectStoreNames.contains('sync_meta')) {
                    db.createObjectStore('sync_meta', { keyPath: 'key' });
                }
            };
        });
    }

    // Request persistent storage quota to prevent browser auto-clearing
    async requestStoragePersistence() {
        if (navigator.storage && navigator.storage.persist) {
            try {
                this.isPersistent = await navigator.storage.persist();
                console.log('[OfflineDB] Storage persistence status:', this.isPersistent ? 'PERSISTENT' : 'TEMPORARY');
            } catch (err) {
                console.warn('[OfflineDB] Storage persistence check error:', err);
            }
        }
    }

    // Generate UUID v4 for client-side idempotency
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

    // Save pending sale into Outbox
    async savePendingSale(saleData) {
        if (!this.db) await this.init();

        const idempotencyKey = saleData.idempotency_key || saleData.client_uuid || this.generateUUID();
        const saleId = saleData.id || `offline_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;

        const record = {
            id: saleId,
            idempotency_key: idempotencyKey,
            client_uuid: idempotencyKey,
            timestamp: Date.now(),
            client_created_at: saleData.client_created_at || new Date().toISOString(),
            status: 'pending',
            sync_attempts: 0,
            last_sync_attempt: null,
            error: null,
            data: {
                ...saleData,
                idempotency_key: idempotencyKey,
                client_uuid: idempotencyKey,
                client_created_at: saleData.client_created_at || new Date().toISOString(),
            }
        };

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const request = store.put(record);

            request.onsuccess = () => {
                console.log('[OfflineDB] Saved pending sale:', record.id, 'Idempotency Key:', idempotencyKey);
                // Dispatch event so UI badges can update immediately
                window.dispatchEvent(new CustomEvent('offlinesale:saved', { detail: record }));
                resolve(record);
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Get all pending sales
    async getPendingSales() {
        if (!this.db) await this.init();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readonly');
            const store = transaction.objectStore('pending_sales');
            const request = store.getAll();

            request.onsuccess = () => {
                const all = request.result || [];
                const pending = all.filter(s => s.status !== 'synced');
                resolve(pending);
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Get pending sales count
    async getPendingCount() {
        if (!this.db) await this.init();
        const pending = await this.getPendingSales();
        return pending.length;
    }

    // Update sale status
    async updateSaleStatus(id, status, error = null) {
        if (!this.db) await this.init();
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
                    if (error) sale.error = error;

                    const updateRequest = store.put(sale);
                    updateRequest.onsuccess = () => resolve(sale);
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    resolve(null);
                }
            };
            getRequest.onerror = () => reject(getRequest.error);
        });
    }

    // Mark sale synced and remove from pending queue
    async markSaleSynced(id) {
        if (!this.db) await this.init();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_sales'], 'readwrite');
            const store = transaction.objectStore('pending_sales');
            const request = store.delete(id);

            request.onsuccess = () => {
                console.log('[OfflineDB] Deleted synced sale from outbox:', id);
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Delete sale
    async deleteSale(id) {
        return this.markSaleSynced(id);
    }

    // Cache catalog data (Products, Categories, Payment Methods, Customers)
    async cacheCatalog({ products = [], categories = [], paymentMethods = [], customers = [] }) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(
                ['cached_products', 'cached_categories', 'cached_payment_methods', 'cached_customers', 'sync_meta'],
                'readwrite'
            );

            if (products && products.length > 0) {
                const prodStore = tx.objectStore('cached_products');
                products.forEach(p => {
                    prodStore.put({
                        id: Number(p.id),
                        name: p.name || '',
                        product_code: p.product_code || p.code || '',
                        barcode: p.barcode || '',
                        unit_price: parseFloat(p.unit_price || p.price || 0),
                        stock_quantity: parseFloat(p.stock_quantity || p.stock || 0),
                        category_id: p.category_id || (p.category ? p.category.id : null),
                        category_name: p.category_name || (p.category ? p.category.name : ''),
                        image_url: p.image_url || p.image || '',
                        has_variants: Boolean(p.has_variants),
                        is_piece_pricing: Boolean(p.is_piece_pricing),
                        piece_factor: p.piece_factor || 1,
                        piece_unit_name: p.piece_unit_name || 'Piece',
                        piece_price: p.piece_price || null,
                        vat_rate: p.vat_rate || 16.0,
                    });
                });
            }

            if (categories && categories.length > 0) {
                const catStore = tx.objectStore('cached_categories');
                categories.forEach(c => catStore.put(c));
            }

            if (paymentMethods && paymentMethods.length > 0) {
                const pmStore = tx.objectStore('cached_payment_methods');
                paymentMethods.forEach(pm => pmStore.put(pm));
            }

            if (customers && customers.length > 0) {
                const custStore = tx.objectStore('cached_customers');
                customers.forEach(cu => custStore.put(cu));
            }

            const metaStore = tx.objectStore('sync_meta');
            metaStore.put({ key: 'last_catalog_sync', timestamp: Date.now() });

            tx.oncomplete = () => {
                console.log(`[OfflineDB] Cached catalog: ${products.length} products, ${categories.length} categories`);
                resolve(true);
            };
            tx.onerror = () => reject(tx.error);
        });
    }

    // Search cached products locally
    async searchLocalProducts(query = '', categoryId = null) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cached_products'], 'readonly');
            const store = transaction.objectStore('cached_products');
            const request = store.getAll();

            request.onsuccess = () => {
                let items = request.result || [];
                const q = query.trim().toLowerCase();

                if (categoryId && categoryId !== 'all') {
                    const catIdNum = Number(categoryId);
                    items = items.filter(p => Number(p.category_id) === catIdNum);
                }

                if (q) {
                    items = items.filter(p => {
                        return (p.name && p.name.toLowerCase().includes(q)) ||
                               (p.barcode && p.barcode.toLowerCase().includes(q)) ||
                               (p.product_code && p.product_code.toLowerCase().includes(q));
                    });
                }

                resolve(items);
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Fast barcode lookup in local cache
    async findLocalProductByBarcode(barcode) {
        if (!this.db) await this.init();
        if (!barcode) return null;

        const cleanBarcode = String(barcode).trim();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cached_products'], 'readonly');
            const store = transaction.objectStore('cached_products');
            const index = store.index('barcode');
            const request = index.get(cleanBarcode);

            request.onsuccess = () => {
                if (request.result) {
                    resolve(request.result);
                } else {
                    // Fallback: search all products if barcode matches product_code
                    const allReq = store.getAll();
                    allReq.onsuccess = () => {
                        const match = (allReq.result || []).find(
                            p => (p.barcode && p.barcode.trim() === cleanBarcode) ||
                                 (p.product_code && p.product_code.trim() === cleanBarcode)
                        );
                        resolve(match || null);
                    };
                    allReq.onerror = () => resolve(null);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Get cached payment methods
    async getLocalPaymentMethods() {
        if (!this.db) await this.init();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['cached_payment_methods'], 'readonly');
            const store = transaction.objectStore('cached_payment_methods');
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    // Log sync activity
    async logSync(action, details) {
        if (!this.db) await this.init();
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
        if (!this.db) await this.init();
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

if (typeof window !== 'undefined') {
    window.offlineDB = offlineDB;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => offlineDB.init());
    } else {
        offlineDB.init();
    }
}
