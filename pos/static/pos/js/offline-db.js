/**
 * IndexedDB Wrapper for Offline Storage
 * Manages local database for offline-first functionality
 */

class OfflineDB {
    constructor() {
        this.dbName = 'POSOfflineDB';
        this.version = 1;
        this.db = null;
    }

    /**
     * Initialize database
     */
    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Products store
                if (!db.objectStoreNames.contains('products')) {
                    const productStore = db.createObjectStore('products', { keyPath: 'id' });
                    productStore.createIndex('barcode', 'barcode', { unique: false });
                    productStore.createIndex('product_code', 'product_code', { unique: false });
                    productStore.createIndex('updated_at', 'updated_at', { unique: false });
                }

                // Categories store
                if (!db.objectStoreNames.contains('categories')) {
                    db.createObjectStore('categories', { keyPath: 'id' });
                }

                // Customers store
                if (!db.objectStoreNames.contains('customers')) {
                    const customerStore = db.createObjectStore('customers', { keyPath: 'id' });
                    customerStore.createIndex('phone', 'phone', { unique: false });
                    customerStore.createIndex('email', 'email', { unique: false });
                }

                // Suppliers store
                if (!db.objectStoreNames.contains('suppliers')) {
                    db.createObjectStore('suppliers', { keyPath: 'id' });
                }

                // Sales store (pending sync)
                if (!db.objectStoreNames.contains('sales')) {
                    const salesStore = db.createObjectStore('sales', { keyPath: 'id', autoIncrement: true });
                    salesStore.createIndex('synced', 'synced', { unique: false });
                    salesStore.createIndex('created_at', 'created_at', { unique: false });
                }

                // Payment methods store
                if (!db.objectStoreNames.contains('payment_methods')) {
                    db.createObjectStore('payment_methods', { keyPath: 'id' });
                }

                // Sync queue store
                if (!db.objectStoreNames.contains('sync_queue')) {
                    const syncStore = db.createObjectStore('sync_queue', { keyPath: 'id', autoIncrement: true });
                    syncStore.createIndex('model', 'model', { unique: false });
                    syncStore.createIndex('created_at', 'created_at', { unique: false });
                }

                // Sync metadata store
                if (!db.objectStoreNames.contains('sync_metadata')) {
                    db.createObjectStore('sync_metadata', { keyPath: 'key' });
                }
            };
        });
    }

    /**
     * Get all records from a store
     */
    async getAll(storeName) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get a single record by ID
     */
    async get(storeName, id) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.get(id);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get records by index
     */
    async getByIndex(storeName, indexName, value) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const index = store.index(indexName);
            const request = index.getAll(value);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Add or update a record
     */
    async put(storeName, data) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.put(data);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Add multiple records
     */
    async putBulk(storeName, dataArray) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);

            let completed = 0;
            const total = dataArray.length;

            dataArray.forEach((data) => {
                const request = store.put(data);
                request.onsuccess = () => {
                    completed++;
                    if (completed === total) {
                        resolve(completed);
                    }
                };
                request.onerror = () => reject(request.error);
            });

            if (total === 0) resolve(0);
        });
    }

    /**
     * Delete a record
     */
    async delete(storeName, id) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(id);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Clear all records from a store
     */
    async clear(storeName) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.clear();

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Search products by barcode or product code
     */
    async searchProduct(query) {
        const products = await this.getAll('products');
        return products.filter(p => 
            p.barcode === query || 
            p.product_code === query ||
            p.name.toLowerCase().includes(query.toLowerCase())
        );
    }

    /**
     * Get products with low stock
     */
    async getLowStockProducts() {
        const products = await this.getAll('products');
        return products.filter(p => p.stock_quantity <= p.low_stock_threshold);
    }

    /**
     * Add sale to sync queue
     */
    async queueSale(saleData) {
        saleData.synced = false;
        saleData.created_at = new Date().toISOString();
        return await this.put('sales', saleData);
    }

    /**
     * Get unsynced sales
     */
    async getUnsyncedSales() {
        return await this.getByIndex('sales', 'synced', false);
    }

    /**
     * Mark sale as synced
     */
    async markSaleSynced(saleId) {
        const sale = await this.get('sales', saleId);
        if (sale) {
            sale.synced = true;
            sale.synced_at = new Date().toISOString();
            await this.put('sales', sale);
        }
    }

    /**
     * Add item to sync queue
     */
    async addToSyncQueue(model, operation, data) {
        const queueItem = {
            model,
            operation, // 'create', 'update', 'delete'
            data,
            created_at: new Date().toISOString(),
            retries: 0
        };
        return await this.put('sync_queue', queueItem);
    }

    /**
     * Get sync queue
     */
    async getSyncQueue() {
        return await this.getAll('sync_queue');
    }

    /**
     * Clear sync queue
     */
    async clearSyncQueue() {
        return await this.clear('sync_queue');
    }

    /**
     * Get last sync timestamp
     */
    async getLastSync() {
        const metadata = await this.get('sync_metadata', 'last_sync');
        return metadata ? metadata.value : null;
    }

    /**
     * Set last sync timestamp
     */
    async setLastSync(timestamp) {
        return await this.put('sync_metadata', {
            key: 'last_sync',
            value: timestamp
        });
    }

    /**
     * Get device ID
     */
    async getDeviceId() {
        let metadata = await this.get('sync_metadata', 'device_id');
        if (!metadata) {
            const deviceId = 'device-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now();
            await this.put('sync_metadata', {
                key: 'device_id',
                value: deviceId
            });
            return deviceId;
        }
        return metadata.value;
    }

    /**
     * Update product stock locally
     */
    async updateProductStock(productId, quantity) {
        const product = await this.get('products', productId);
        if (product) {
            product.stock_quantity = quantity;
            product.updated_at = new Date().toISOString();
            await this.put('products', product);
            
            // Add to sync queue
            await this.addToSyncQueue('product', 'update', {
                id: productId,
                stock_quantity: quantity
            });
        }
    }
}

// Export singleton instance
const offlineDB = new OfflineDB();
