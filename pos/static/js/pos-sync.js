/**
 * Front Office POS Real-Time Synchronization & Local Product Catalog Cache Engine
 * - Zero-latency (<3ms) local catalog search & barcode scanning
 * - Server-Sent Events (SSE) live push listener for Back Office price/stock adjustments
 * - Automatic offline checkout buffering and auto-sync queue
 */

class POSSyncEngine {
  constructor(options = {}) {
    this.catalogEndpoint = options.catalogEndpoint || '/pos/api/sync/catalog/';
    this.streamEndpoint = options.streamEndpoint || '/pos/api/sync/stream/';
    this.pollEndpoint = options.pollEndpoint || '/pos/api/sync/poll/';
    this.offlineSyncEndpoint = options.offlineSyncEndpoint || '/pos/api/sync/offline-sales/';
    
    this.products = [];
    this.categories = [];
    this.productsMap = new Map();
    this.barcodeMap = new Map();
    this.storeSettings = null;
    
    this.eventSource = null;
    this.pollInterval = null;
    this.lastSyncTime = null;
    this.syncStatus = 'disconnected'; // 'connected' | 'reconnecting' | 'offline'
    this.sseFailures = 0;
    
    this.statusCallbacks = [];
    this.productUpdateCallbacks = [];
    
    this.init();
  }

  async init() {
    this.loadFromLocalStorage();
    await this.fetchCatalog();
    this.connectSSE();
    this.setupNetworkListeners();
    this.flushOfflineQueue();
  }

  /* ==================== Local Catalog Cache ==================== */

  loadFromLocalStorage() {
    try {
      const cached = localStorage.getItem('pos_cached_catalog');
      if (cached) {
        const data = JSON.parse(cached);
        this.indexProducts(data.products || [], data.categories || []);
        this.lastSyncTime = data.server_time || null;
      }
      const cachedSettings = localStorage.getItem('pos_cached_settings');
      if (cachedSettings) {
        this.storeSettings = JSON.parse(cachedSettings);
      }
    } catch (e) {
      console.warn('[POS Sync] Error loading cached catalog:', e);
    }
  }

  saveToLocalStorage(data) {
    try {
      localStorage.setItem('pos_cached_catalog', JSON.stringify({
        server_time: data.server_time,
        products: data.products,
        categories: data.categories
      }));
      if (data.store_settings) {
        this.storeSettings = data.store_settings;
        localStorage.setItem('pos_cached_settings', JSON.stringify(data.store_settings));
      }
    } catch (e) {
      console.warn('[POS Sync] Error caching catalog:', e);
    }
  }

  async fetchCatalog() {
    try {
      const resp = await fetch(this.catalogEndpoint, { credentials: 'same-origin' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.success && Array.isArray(data.products)) {
        this.indexProducts(data.products, data.categories || []);
        this.lastSyncTime = data.server_time;
        this.saveToLocalStorage(data);
        this.updateStatus('connected');
        window.dispatchEvent(new CustomEvent('pos:catalog-loaded', { detail: { count: this.products.length } }));
      }
    } catch (err) {
      console.warn('[POS Sync] Fetch catalog failed, using cached data if available:', err);
      if (this.products.length === 0) {
        this.updateStatus('offline');
      }
    }
  }

  indexProducts(products, categories) {
    this.products = products;
    this.categories = categories;
    this.productsMap.clear();
    this.barcodeMap.clear();

    for (const p of products) {
      this.productsMap.set(Number(p.id), p);
      if (p.barcode) {
        this.barcodeMap.set(String(p.barcode).trim(), p);
      }
      if (p.product_code) {
        this.barcodeMap.set(String(p.product_code).trim().toLowerCase(), p);
      }
    }
  }

  /* ==================== High-Speed Search APIs ==================== */

  findByBarcode(barcode) {
    if (!barcode) return null;
    const clean = String(barcode).trim();
    return this.barcodeMap.get(clean) || this.barcodeMap.get(clean.toLowerCase()) || null;
  }

  getById(id) {
    return this.productsMap.get(Number(id)) || null;
  }

  search(query, categoryId = null, limit = 50) {
    const q = (query || '').trim().toLowerCase();
    const cat = categoryId ? Number(categoryId) : null;

    const results = [];
    for (const p of this.products) {
      if (cat && Number(p.category_id) !== cat) continue;
      if (!q) {
        results.push(p);
      } else {
        const matchName = p.name && p.name.toLowerCase().includes(q);
        const matchCode = p.product_code && p.product_code.toLowerCase().includes(q);
        const matchBarcode = p.barcode && p.barcode.includes(q);
        if (matchName || matchCode || matchBarcode) {
          results.push(p);
        }
      }
      if (results.length >= limit) break;
    }
    return results;
  }

  /* ==================== Real-Time Sync Stream (SSE) ==================== */

  connectSSE() {
    if (this.eventSource) {
      this.eventSource.close();
    }

    try {
      this.eventSource = new EventSource(this.streamEndpoint);

      this.eventSource.addEventListener('connect', (e) => {
        this.sseFailures = 0;
        this.updateStatus('connected');
        if (this.pollInterval) {
          clearInterval(this.pollInterval);
          this.pollInterval = null;
        }
      });

      this.eventSource.addEventListener('product_updated', (e) => {
        try {
          const ev = JSON.parse(e.data);
          this.handleProductUpdate(ev.payload || ev);
        } catch (err) {
          console.error('[POS Sync] Error handling product update:', err);
        }
      });

      this.eventSource.addEventListener('sale_completed', (e) => {
        try {
          const ev = JSON.parse(e.data);
          window.dispatchEvent(new CustomEvent('pos:sale-broadcast', { detail: ev.payload || ev }));
        } catch (err) {}
      });

      this.eventSource.addEventListener('shift_event', (e) => {
        try {
          const ev = JSON.parse(e.data);
          window.dispatchEvent(new CustomEvent('pos:shift-broadcast', { detail: ev.payload || ev }));
        } catch (err) {}
      });

      this.eventSource.addEventListener('settings_updated', (e) => {
        try {
          const ev = JSON.parse(e.data);
          const payload = ev.payload || ev;
          this.storeSettings = Object.assign(this.storeSettings || {}, payload);
          localStorage.setItem('pos_cached_settings', JSON.stringify(this.storeSettings));
          window.dispatchEvent(new CustomEvent('pos:settings-updated', { detail: this.storeSettings }));
        } catch (err) {
          console.error('[POS Sync] Error handling settings update:', err);
        }
      });

      this.eventSource.onerror = (e) => {
        this.sseFailures++;
        if (this.eventSource.readyState === EventSource.CLOSED) {
          this.updateStatus('reconnecting');
        }
        // If SSE fails multiple times, enable polling fallback
        if (this.sseFailures >= 3 && !this.pollInterval) {
          this.startPollingFallback();
        }
      };

    } catch (err) {
      console.warn('[POS Sync] EventSource not supported, fallback to polling:', err);
      this.startPollingFallback();
    }
  }

  startPollingFallback() {
    if (this.pollInterval) return;
    this.pollInterval = setInterval(async () => {
      await this.pollEvents();
    }, 5000);
  }

  async pollEvents() {
    try {
      const url = `${this.pollEndpoint}?since=${encodeURIComponent(this.lastSyncTime || '')}`;
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.success && Array.isArray(data.events)) {
        this.updateStatus('connected');
        for (const ev of data.events) {
          if (ev.type === 'product_updated') {
            this.handleProductUpdate(ev.payload);
          } else if (ev.type === 'settings_updated') {
            const payload = ev.payload || ev;
            this.storeSettings = Object.assign(this.storeSettings || {}, payload);
            localStorage.setItem('pos_cached_settings', JSON.stringify(this.storeSettings));
            window.dispatchEvent(new CustomEvent('pos:settings-updated', { detail: this.storeSettings }));
          }
        }
        if (data.server_time) {
          this.lastSyncTime = data.server_time;
        }
      }
    } catch (e) {
      this.updateStatus('offline');
    }
  }

  handleProductUpdate(item) {
    if (!item || !item.product_id) return;
    const prodId = Number(item.product_id);
    let existing = this.productsMap.get(prodId);

    if (existing) {
      // Update properties
      if (item.unit_price !== undefined) existing.unit_price = Number(item.unit_price);
      if (item.stock_quantity !== undefined) existing.stock_quantity = Number(item.stock_quantity);
      if (item.name) existing.name = item.name;
      if (item.barcode) existing.barcode = item.barcode;
      if (item.tax_rate !== undefined) existing.tax_rate = Number(item.tax_rate);
    } else {
      existing = {
        id: prodId,
        name: item.name || '',
        barcode: item.barcode || '',
        product_code: item.product_code || '',
        unit_price: Number(item.unit_price || 0),
        cost_price: Number(item.cost_price || 0),
        stock_quantity: Number(item.stock_quantity || 0),
        tax_rate: Number(item.tax_rate || 0),
        category_id: item.category_id,
        category_name: 'General',
      };
      this.products.push(existing);
    }

    this.indexProducts(this.products, this.categories);
    this.notifyProductUpdated(existing);
    window.dispatchEvent(new CustomEvent('pos:product-updated', { detail: existing }));
  }

  /* ==================== Offline Sales Queue & Sync ==================== */

  getOfflineQueue() {
    try {
      const q = localStorage.getItem('pos_offline_sales_queue');
      return q ? JSON.parse(q) : [];
    } catch (e) {
      return [];
    }
  }

  queueOfflineSale(saleData) {
    try {
      const queue = this.getOfflineQueue();
      saleData.client_uuid = saleData.client_uuid || `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      saleData.queued_at = new Date().toISOString();
      queue.push(saleData);
      localStorage.setItem('pos_offline_sales_queue', JSON.stringify(queue));
      return saleData.client_uuid;
    } catch (e) {
      console.error('[POS Sync] Failed to queue offline sale:', e);
      return null;
    }
  }

  async flushOfflineQueue() {
    const queue = this.getOfflineQueue();
    if (!queue.length) return;

    try {
      const resp = await fetch(this.offlineSyncEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ sales: queue })
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      if (result.success) {
        localStorage.removeItem('pos_offline_sales_queue');
        window.dispatchEvent(new CustomEvent('pos:offline-sales-synced', { detail: result }));
      }
    } catch (e) {
      console.warn('[POS Sync] Could not flush offline sales queue yet:', e);
    }
  }

  /* ==================== Network Status & UI ==================== */

  setupNetworkListeners() {
    window.addEventListener('online', () => {
      this.updateStatus('reconnecting');
      this.connectSSE();
      this.fetchCatalog();
      this.flushOfflineQueue();
    });

    window.addEventListener('offline', () => {
      this.updateStatus('offline');
    });
  }

  updateStatus(newStatus) {
    if (this.syncStatus === newStatus) return;
    this.syncStatus = newStatus;
    for (const cb of this.statusCallbacks) {
      try { cb(newStatus); } catch (e) {}
    }
    this.renderSyncBadge();
  }

  onStatusChange(cb) {
    this.statusCallbacks.push(cb);
  }

  notifyProductUpdated(product) {
    for (const cb of this.productUpdateCallbacks) {
      try { cb(product); } catch (e) {}
    }
  }

  onProductUpdate(cb) {
    this.productUpdateCallbacks.push(cb);
  }

  renderSyncBadge() {
    const el = document.getElementById('posSyncStatusBadge');
    if (!el) return;

    if (this.syncStatus === 'connected') {
      el.className = 'badge rounded-pill bg-success bg-opacity-15 text-success border border-success border-opacity-25 px-2 py-1';
      el.innerHTML = '<i class="bi bi-broadcast me-1"></i>Live Sync';
      el.title = 'Real-time synchronization active with Back Office';
    } else if (this.syncStatus === 'reconnecting') {
      el.className = 'badge rounded-pill bg-warning bg-opacity-15 text-warning-emphasis border border-warning border-opacity-25 px-2 py-1';
      el.innerHTML = '<i class="bi bi-arrow-repeat spin me-1"></i>Syncing...';
      el.title = 'Re-establishing live connection...';
    } else {
      const offlineQueueCount = this.getOfflineQueue().length;
      el.className = 'badge rounded-pill bg-danger bg-opacity-15 text-danger border border-danger border-opacity-25 px-2 py-1';
      el.innerHTML = `<i class="bi bi-wifi-off me-1"></i>Offline Mode${offlineQueueCount ? ` (${offlineQueueCount} queued)` : ''}`;
      el.title = 'Operating in offline mode with cached catalog';
    }
  }
}

// Global instance initialization helper
window.initPOSSync = function(options) {
  if (!window.posSyncEngine) {
    window.posSyncEngine = new POSSyncEngine(options);
  }
  return window.posSyncEngine;
};
