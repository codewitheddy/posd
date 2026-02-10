# 🏪 Cloud-Enabled Offline-First POS System

A modern, professional Point of Sale system with cloud synchronization and offline-first architecture.

## ✨ Key Features

### 🌐 Hybrid Online-Offline
- Works without internet connection
- Automatic cloud synchronization
- Local-first for instant performance
- Background sync when online

### 💳 Complete POS Functionality
- Product management with barcode scanning
- Sales processing with multiple payment methods
- Customer loyalty program with tiers
- Inventory tracking and alerts
- Supplier and purchase management
- Comprehensive reporting

### 👥 User Management
- Role-based access control
- Multiple user roles (Admin, Manager, Cashier, Stock Manager)
- Activity logging
- User profiles and permissions

### 📊 Business Intelligence
- Real-time dashboard
- Sales reports by date/cashier
- Inventory reports
- Low stock alerts
- Expiry tracking
- Write-off reports

### 🔄 Cart Persistence
- Cart survives page refresh
- Automatic save and restore
- Smart stock validation
- Customer and discount preservation

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- pip package manager

### Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate

# 3. Create superuser
python manage.py createsuperuser

# 4. Start server
python manage.py runserver
```

### Access the System
- **Web Interface**: http://localhost:8000/
- **API Documentation**: http://localhost:8000/api/v1/docs/
- **Admin Panel**: http://localhost:8000/admin/

## 📚 Documentation

Comprehensive documentation is available in the [`docs/`](docs/) folder:

### Quick Links
- **[Getting Started](docs/setup/START_HERE_CLOUD.md)** - Start here!
- **[Cloud Deployment](docs/deployment/CLOUD_DEPLOYMENT_GUIDE.md)** - Deploy to production
- **[Database Setup](docs/deployment/PRODUCTION_DATABASE_GUIDE.md)** - PostgreSQL for production
- **[Features Guide](docs/features/)** - All features explained
- **[Architecture](docs/architecture/ARCHITECTURE.md)** - System design

### Documentation Structure
```
docs/
├── setup/          # Installation and configuration
├── features/       # Feature guides and tutorials
├── deployment/     # Cloud deployment guides
├── architecture/   # Technical architecture
├── portable/       # Desktop app distribution
└── archive/        # Historical notes
```

**[📖 Browse All Documentation](docs/README.md)**

## 🎯 Use Cases

### Retail Stores
- Fast checkout with barcode scanning
- Inventory management
- Customer loyalty program
- Multi-location support

### Restaurants & Cafes
- Quick order processing
- Table management
- Kitchen integration
- Daily reports

### Supermarkets
- High-volume transactions
- Bulk product management
- Expiry tracking
- Supplier management

### Mobile Sales
- Works offline at events
- Syncs when back online
- Portable on tablets
- No internet required

## 🏗️ Technology Stack

### Backend
- **Django 6.0** - Web framework
- **Django REST Framework** - API
- **PostgreSQL** - Production database (recommended)
- **SQLite** - Development database

### Frontend
- **HTML/CSS/JavaScript** - Web interface
- **Bootstrap 5** - UI framework
- **Service Worker** - Offline capability
- **IndexedDB** - Local storage

### Features
- **JWT Authentication** - Secure API access
- **Offline-First** - Works without internet
- **Auto-Sync** - Background synchronization
- **PWA** - Progressive Web App

## 📊 System Requirements

### Development
- Python 3.8+
- 2GB RAM
- 1GB disk space
- Any modern browser

### Production (Small-Medium)
- Python 3.8+
- 4GB RAM
- PostgreSQL database
- 50GB disk space
- Cloud hosting (DigitalOcean, AWS, Azure)

### Production (Large Scale)
- Python 3.8+
- 16GB+ RAM
- PostgreSQL with read replicas
- 200GB+ disk space
- Load balancer
- Redis cache

## 🚀 Deployment Options

### Option 1: Local Development
```bash
python manage.py runserver
```
Perfect for testing and development.

### Option 2: Cloud Deployment
Deploy to:
- **Heroku** - Easiest ($7-50/month)
- **DigitalOcean** - Simple ($12-36/month)
- **AWS** - Scalable ($30-100/month)
- **Azure** - Enterprise ($30-100/month)

**[📖 Deployment Guide](docs/deployment/CLOUD_DEPLOYMENT_GUIDE.md)**

### Option 3: Desktop Application
Build standalone desktop app:
```bash
pyinstaller pos_system.spec
```

**[📖 Build Guide](docs/portable/BUILD_EXECUTABLE.md)**

## 🔒 Security Features

- ✅ JWT authentication
- ✅ Role-based access control
- ✅ HTTPS encryption
- ✅ CORS protection
- ✅ CSRF protection
- ✅ Secure password hashing
- ✅ Activity logging

## 📈 Performance

### Local Operations
- Product search: <50ms
- Sale creation: <100ms
- Cart updates: Instant

### With PostgreSQL
- Handles 10,000+ products
- Supports 100+ concurrent users
- Processes 1,000+ transactions/hour
- Sub-second query response

## 🎨 Screenshots

### Dashboard
![Dashboard](docs/screenshots/dashboard.png)

### POS Screen
![POS Screen](docs/screenshots/pos-screen.png)

### Reports
![Reports](docs/screenshots/reports.png)

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## 🆘 Support

### Documentation
- [Complete Documentation](docs/README.md)
- [Quick Reference](docs/QUICK_REFERENCE.md)
- [FAQ](docs/FAQ.md)

### Resources
- API Documentation: http://localhost:8000/api/v1/docs/
- Admin Panel: http://localhost:8000/admin/

## 🎉 What's New

### Version 2.0 (Current)
- ✅ Cloud-enabled with offline-first architecture
- ✅ REST API with JWT authentication
- ✅ Automatic data synchronization
- ✅ Cart persistence
- ✅ Multi-location support
- ✅ PostgreSQL support for production
- ✅ Comprehensive documentation

**[📖 Full Changelog](docs/archive/CHANGELOG.md)**

## 🗺️ Roadmap

### Planned Features
- [ ] WebSocket for real-time updates
- [ ] Push notifications
- [ ] Mobile apps (iOS/Android)
- [ ] Advanced analytics
- [ ] Multi-currency support
- [ ] Multi-language support

**[📖 Future Enhancements](docs/FUTURE_ENHANCEMENTS.md)**

## 📞 Contact

For questions, issues, or feature requests, please open an issue on GitHub.

---

**Built with ❤️ for modern retail businesses**

**[Get Started Now](docs/setup/START_HERE_CLOUD.md)** | **[View Documentation](docs/README.md)** | **[Deploy to Cloud](docs/deployment/CLOUD_DEPLOYMENT_GUIDE.md)**
