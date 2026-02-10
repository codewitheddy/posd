# Offline-First POS - Quick Start Guide

## What's New?

Your POS system now works **online AND offline** with automatic data synchronization!

## Key Features

🌐 **Works Offline** - Process sales without internet
💾 **Auto-Sync** - Data syncs automatically when online
⚡ **Fast** - Local-first for instant performance
🔄 **Multi-Location** - Sync across multiple stores
🔒 **Secure** - JWT authentication with encryption

## Quick Setup (5 Minutes)

### 1. Install New Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- Django REST Framework (API)
- JWT Authentication (Security)
- CORS Headers (Cross-origin support)
- API Documentation (Swagger)

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Start Server

```bash
python manage.py runserver
```

### 4. Test API

Visit: `http://localhost:8000/api/v1/docs/`

You'll see interactive API documentation!

## How It Works

### Online Mode
```
User Action → Local Storage → API Call → Cloud Database
                    ↓
              Update UI (instant)
```

### Offline Mode
```
User Action → Local Storage → Sync Queue
                    ↓
              Update UI (instant)
                    ↓
         (When online) → API Call → Cloud Database
```

## Using the API

### 1. Get Authentication Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### 2. List Products

```bash
curl -X GET http://localhost:8000/api/v1/products/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 3. Sync Data

```bash
curl -X POST http://localhost:8000/api/v1/sync/pull/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "device-123",
    "last_sync": null
  }'
```

## Available API Endpoints

### Authentication
- `POST /api/v1/auth/token/` - Login (get token)
- `POST /api/v1/auth/token/refresh/` - Refresh token

### Products
- `GET /api/v1/products/` - List all products
- `GET /api/v1/products/{id}/` - Get product details
- `POST /api/v1/products/` - Create product
- `PUT /api/v1/products/{id}/` - Update product
- `DELETE /api/v1/products/{id}/` - Delete product
- `GET /api/v1/products/low_stock/` - Get low stock products
- `GET /api/v1/products/expiring_soon/` - Get expiring products

### Categories
- `GET /api/v1/categories/` - List categories
- `POST /api/v1/categories/` - Create category

### Customers
- `GET /api/v1/customers/` - List customers
- `POST /api/v1/customers/` - Create customer
- `POST /api/v1/customers/{id}/add_points/` - Add loyalty points

### Sales
- `GET /api/v1/sales/` - List sales
- `GET /api/v1/sales/today/` - Today's sales
- `POST /api/v1/sales/` - Create sale

### Sync
- `POST /api/v1/sync/pull/` - Pull server updates
- `POST /api/v1/sync/push/` - Push local changes
- `GET /api/v1/sync/status/` - Check sync status

### Documentation
- `GET /api/v1/docs/` - Interactive API docs (Swagger UI)
- `GET /api/v1/schema/` - OpenAPI schema

## Offline Features

### Service Worker
Automatically caches resources for offline use:
- Static files (CSS, JS, images)
- API responses
- Product data
- Customer data

### IndexedDB
Local database stores:
- Products
- Categories
- Customers
- Suppliers
- Unsynced sales
- Sync queue

### Background Sync
Automatically syncs when:
- Connection restored
- Every 1 minute (configurable)
- On demand (manual trigger)

## Testing Offline Mode

### 1. Open Browser DevTools
- Chrome: F12 → Network tab
- Firefox: F12 → Network tab

### 2. Enable Offline Mode
- Check "Offline" checkbox in Network tab

### 3. Try Using POS
- Search products (works from local cache)
- Process sales (queued for sync)
- View customers (from local storage)

### 4. Go Back Online
- Uncheck "Offline" checkbox
- Watch automatic sync happen!

## Configuration

### Sync Interval

Edit `pos/static/pos/js/sync-manager.js`:

```javascript
this.autoSyncIntervalMs = 60000; // 1 minute (default)
// Change to 300000 for 5 minutes
// Change to 30000 for 30 seconds
```

### JWT Token Lifetime

Edit `pos_system/settings.py`:

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),  # 24 hours
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),  # 30 days
}
```

### CORS Origins

Edit `pos_system/settings.py`:

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://yourdomain.com",  # Add your domain
]
```

## Monitoring Sync Status

### JavaScript Console

```javascript
// Get sync statistics
const stats = await syncManager.getSyncStats();
console.log(stats);

// Output:
// {
//   unsyncedSales: 3,
//   queuedChanges: 5,
//   lastSync: "2026-02-10T10:30:00Z",
//   isOnline: true,
//   syncInProgress: false
// }
```

### Manual Sync

```javascript
// Force sync now
await syncManager.syncNow();
```

### Listen for Sync Events

```javascript
window.addEventListener('syncstatus', (event) => {
    console.log('Sync status:', event.detail.status);
    // status: 'syncing', 'synced', 'error'
});
```

## Common Use Cases

### 1. Mobile POS (Tablet/Phone)
- Works offline at events/markets
- Syncs when back at store with WiFi
- Fast local operations

### 2. Multiple Store Locations
- Each location has local cache
- All sync to central cloud database
- Real-time inventory across locations

### 3. Poor Internet Areas
- Continue working during outages
- Queue all transactions
- Sync when connection improves

### 4. Backup & Disaster Recovery
- Data automatically backed up to cloud
- Local copy always available
- No data loss during outages

## Troubleshooting

### API Not Working
```bash
# Check if server is running
python manage.py runserver

# Check migrations
python manage.py migrate

# Check for errors
python manage.py check
```

### Service Worker Not Loading
- Ensure HTTPS (or localhost)
- Check browser console for errors
- Clear browser cache
- Re-register service worker

### Sync Failing
- Check authentication token
- Verify internet connection
- Check browser console
- Review server logs

### Database Issues
```bash
# Reset database (CAUTION: Deletes data)
python manage.py flush

# Run migrations again
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

## Next Steps

### For Development
1. ✅ Test API endpoints
2. ✅ Test offline mode
3. ✅ Review API documentation
4. ⬜ Customize sync behavior
5. ⬜ Add custom API endpoints

### For Production
1. ⬜ Choose cloud provider
2. ⬜ Set up PostgreSQL database
3. ⬜ Configure environment variables
4. ⬜ Deploy application
5. ⬜ Set up SSL certificate
6. ⬜ Configure domain
7. ⬜ Test from multiple devices

## Resources

- **API Docs**: http://localhost:8000/api/v1/docs/
- **Admin Panel**: http://localhost:8000/admin/
- **Deployment Guide**: See `CLOUD_DEPLOYMENT_GUIDE.md`
- **Architecture**: See `OFFLINE_SYNC_ARCHITECTURE.md`

## Support

### Check Logs
```bash
# Django logs
python manage.py runserver --verbosity 2

# Browser console
F12 → Console tab
```

### Test API
Use tools like:
- Postman
- Insomnia
- curl
- Browser DevTools

### Common Errors

**401 Unauthorized**
- Token expired or invalid
- Get new token from `/api/v1/auth/token/`

**403 Forbidden**
- User doesn't have permission
- Check user role and permissions

**404 Not Found**
- Check URL spelling
- Verify endpoint exists in docs

**500 Server Error**
- Check server logs
- Verify database connection
- Check migrations

## Tips

💡 **Use API Docs** - Interactive testing at `/api/v1/docs/`
💡 **Test Offline** - Use browser DevTools Network tab
💡 **Monitor Sync** - Check browser console for sync logs
💡 **Backup Data** - Cloud automatically backs up
💡 **Multiple Devices** - Each device syncs independently

## Conclusion

Your POS system is now a modern, offline-first application that works anywhere, anytime. Process sales without worrying about internet connectivity, and let the system handle synchronization automatically!

**Happy selling! 🚀**
