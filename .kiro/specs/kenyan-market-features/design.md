# Kenyan Market Features - Design Document

## Overview

This document outlines the technical design for implementing offline mode with sync and mobile-responsive improvements for the Kenyan market.

## Architecture

### Offline Mode Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   UI Layer   │  │ Service      │  │  IndexedDB   │     │
│  │              │  │ Worker       │  │              │     │
│  │  - POS       │  │              │  │  - Products  │     │
│  │  - Dashboard │  │  - Cache     │  │  - Customers │     │
│  │  - Reports   │  │  - Sync      │  │  - Sales     │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                            │                                 │
└────────────────────────────┼─────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Django API    │
                    │                 │
                    │  - REST API     │
                    │  - WebSocket    │
                    └─────────────────┘
```

### Mobile-Responsive Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Responsive Design                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Mobile     │  │   Tablet     │  │   Desktop    │     │
│  │   <768px     │  │  768-1024px  │  │   >1024px    │     │
│  │              │  │              │  │              │     │
│  │  - Bottom    │  │  - Sidebar   │  │  - Full      │     │
│  │    Nav       │  │    Nav       │  │    Nav       │     │
│  │  - Touch     │  │  - Hybrid    │  │  - Mouse     │     │
│  │    Optimized │  │    Interface │  │    Optimized │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│              Shared Components & Logic                       │
└─────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. Offline Manager (JavaScript)

**File**: `posd/pos/static/js/offline-manager.js`

```javascript
class OfflineManager {
    constructor() {
        this.db = null;
        this.isOnline = navigator.onLine;
        this.syncQueue = [];
        this.init();
    }
    
    async init() {
        // Initialize IndexedDB
        // Setup event listeners
        // Start sync worker
    }
    
    async cacheProducts(products) {
        // Store products in IndexedDB
    }
    
    async getProducts() {
        // Retrieve products from IndexedDB
    }
    
    async saveSaleOffline(saleData) {
        // Save sale to IndexedDB with pending status
        // Add to sync queue
    }
    
    async syncPendingSales() {
        // Sync all pending sales to server
        // Update sync status
        // Handle conflicts
    }
    
    onConnectionChange(callback) {
        // Listen for online/offline events
    }
}
```

### 2. Service Worker

**File**: `posd/pos/static/sw.js`

```javascript
// Cache strategy
const CACHE_NAME = 'pos-v1';
const urlsToCache = [
    '/static/css/',
    '/static/js/',
    '/static/images/',
];

// Install event
self.addEventListener('install', event => {
    // Cache static assets
});

// Fetch event
self.addEventListener('fetch', event => {
    // Network first, fallback to cache
    // Cache API responses
});

// Background sync
self.addEventListener('sync', event => {
    if (event.tag === 'sync-sales') {
        // Sync pending sales
    }
});
```

### 3. Connection Status Component

**File**: `posd/pos/templates/pos/components/connection_status.html`

```html
<div id="connection-status" class="connection-status">
    <div class="status-indicator">
        <i class="fas fa-wifi"></i>
        <span class="status-text">Online</span>
    </div>
    <div class="sync-info">
        <span class="pending-count">0</span> pending
    </div>
</div>
```

### 4. Mobile Navigation Component

**File**: `posd/pos/templates/pos/components/mobile_nav.html`

```html
<!-- Bottom Navigation for Mobile -->
<nav class="mobile-bottom-nav d-md-none">
    <a href="{% url 'pos_screen' %}" class="nav-item">
        <i class="fas fa-cash-register"></i>
        <span>POS</span>
    </a>
    <a href="{% url 'dashboard' %}" class="nav-item">
        <i class="fas fa-chart-line"></i>
        <span>Dashboard</span>
    </a>
    <a href="{% url 'product_list' %}" class="nav-item">
        <i class="fas fa-boxes"></i>
        <span>Products</span>
    </a>
    <a href="#" class="nav-item" data-bs-toggle="offcanvas" data-bs-target="#mobileMenu">
        <i class="fas fa-bars"></i>
        <span>More</span>
    </a>
</nav>
```

## Database Schema (IndexedDB)

### Products Store
```javascript
{
    keyPath: 'id',
    indexes: [
        { name: 'barcode', unique: false },
        { name: 'name', unique: false },
        { name: 'category', unique: false }
    ]
}
```

### Customers Store
```javascript
{
    keyPath: 'id',
    indexes: [
        { name: 'phone', unique: false },
        { name: 'name', unique: false }
    ]
}
```

### Pending Sales Store
```javascript
{
    keyPath: 'localId',
    indexes: [
        { name: 'timestamp', unique: false },
        { name: 'syncStatus', unique: false }
    ]
}
```

### Sync Queue Store
```javascript
{
    keyPath: 'id',
    autoIncrement: true,
    indexes: [
        { name: 'type', unique: false },
        { name: 'status', unique: false },
        { name: 'retryCount', unique: false }
    ]
}
```

## API Endpoints

### Sync Endpoints

```python
# Batch sync endpoint
POST /api/v1/sync/sales/
{
    "sales": [
        {
            "local_id": "uuid",
            "timestamp": "2024-02-13T10:30:00Z",
            "items": [...],
            "total": 1500.00,
            "payment_method": "cash"
        }
    ]
}

Response:
{
    "synced": [
        {
            "local_id": "uuid",
            "server_id": 123,
            "status": "success"
        }
    ],
    "failed": []
}

# Get cached data
GET /api/v1/cache/products/?last_sync=2024-02-13T10:00:00Z
Response:
{
    "products": [...],
    "timestamp": "2024-02-13T10:30:00Z",
    "has_more": false
}
```

## Mobile Responsive Design

### CSS Framework Approach

```css
/* Mobile First Approach */

/* Base styles (Mobile) */
.container {
    padding: 1rem;
}

.card {
    margin-bottom: 1rem;
}

/* Tablet */
@media (min-width: 768px) {
    .container {
        padding: 2rem;
    }
    
    .card {
        margin-bottom: 1.5rem;
    }
}

/* Desktop */
@media (min-width: 1024px) {
    .container {
        max-width: 1200px;
        margin: 0 auto;
    }
}
```

### Touch Optimization

```css
/* Larger touch targets */
.btn-mobile {
    min-height: 44px;
    min-width: 44px;
    padding: 12px 20px;
}

/* Prevent text selection on buttons */
.touch-action-none {
    touch-action: none;
    user-select: none;
}

/* Smooth scrolling */
.scroll-container {
    -webkit-overflow-scrolling: touch;
    overflow-y: auto;
}
```

## Performance Optimization

### 1. Lazy Loading
```javascript
// Intersection Observer for images
const imageObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            imageObserver.unobserve(img);
        }
    });
});
```

### 2. Code Splitting
```javascript
// Dynamic imports for heavy components
async function loadReports() {
    const module = await import('./reports.js');
    module.init();
}
```

### 3. Data Pagination
```python
# API pagination
class ProductListView(APIView):
    def get(self, request):
        page = request.GET.get('page', 1)
        page_size = request.GET.get('page_size', 20)
        # Return paginated results
```

## Sync Strategy

### Conflict Resolution

```python
def resolve_conflict(local_sale, server_sale):
    """
    Conflict resolution strategy:
    1. Server wins for product data
    2. Local wins for new sales (queue for sync)
    3. Timestamp-based for updates
    """
    if local_sale['timestamp'] > server_sale['timestamp']:
        return local_sale
    return server_sale
```

### Retry Logic

```javascript
class SyncManager {
    async syncWithRetry(data, maxRetries = 5) {
        let retryCount = 0;
        const delays = [1000, 5000, 15000, 30000, 60000];
        
        while (retryCount < maxRetries) {
            try {
                return await this.sync(data);
            } catch (error) {
                retryCount++;
                if (retryCount >= maxRetries) throw error;
                await this.delay(delays[retryCount - 1]);
            }
        }
    }
}
```

## Progressive Web App (PWA)

### Manifest File

**File**: `posd/pos/static/manifest.json`

```json
{
    "name": "POS System",
    "short_name": "POS",
    "description": "Point of Sale System",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0f172a",
    "theme_color": "#6366f1",
    "icons": [
        {
            "src": "/static/images/icon-192.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/static/images/icon-512.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
}
```

## Testing Strategy

### Offline Mode Testing
1. Test with Chrome DevTools offline mode
2. Test with throttled network (3G)
3. Test sync after extended offline period
4. Test conflict resolution
5. Test data integrity after sync

### Mobile Testing
1. Test on real devices (Android, iOS)
2. Test different screen sizes
3. Test touch interactions
4. Test landscape/portrait
5. Test with slow network

## Security Considerations

1. **Offline Data Encryption**: Encrypt sensitive data in IndexedDB
2. **Sync Authentication**: Use JWT tokens for sync API
3. **Data Validation**: Validate all synced data on server
4. **Rate Limiting**: Limit sync requests to prevent abuse
5. **Data Expiration**: Auto-delete old offline data

## Implementation Phases

### Phase 1: Basic Offline (Week 1-2)
- IndexedDB setup
- Product caching
- Offline sale storage
- Connection status indicator

### Phase 2: Sync Implementation (Week 3-4)
- Background sync
- Retry logic
- Conflict resolution
- Sync status UI

### Phase 3: Mobile Optimization (Week 5-6)
- Responsive layouts
- Touch optimization
- Bottom navigation
- Mobile POS interface

### Phase 4: Performance & PWA (Week 7-8)
- Service Worker
- Lazy loading
- Code splitting
- PWA manifest
- Performance testing

## Success Metrics

- Offline transaction success rate: >95%
- Sync success rate: >98%
- Mobile page load time: <3s on 3G
- Lighthouse mobile score: >90
- User satisfaction: >4.5/5
