# System Architecture

Visual representation of the POS system architecture and data flow.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     POS SYSTEM                              │
│                  (Django Application)                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Frontend   │    │   Backend    │    │   Database   │
│  (Templates) │◄───┤   (Views)    │◄───┤  (SQLite/    │
│  Bootstrap 5 │    │   Django     │    │  PostgreSQL) │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Application Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Dashboard │  │   POS    │  │ Products │  │ Reports  │   │
│  │  View    │  │  Screen  │  │   View   │  │   View   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                     BUSINESS LOGIC LAYER                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    Views (views.py)                   │  │
│  │  • Product Management  • Sale Processing             │  │
│  │  • Invoice Generation  • Report Generation           │  │
│  │  • VAT Calculation     • Discount Calculation        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      DATA ACCESS LAYER                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Models (models.py)                   │  │
│  │  • Category  • Product  • Sale  • SaleItem           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                       DATABASE LAYER                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         SQLite (Dev) / PostgreSQL (Prod)             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Data Model Relationships

```
┌──────────────┐
│   Category   │
│──────────────│
│ id (PK)      │
│ name         │
│ created_at   │
└──────────────┘
        │
        │ 1:N
        │
        ▼
┌──────────────┐         ┌──────────────┐
│   Product    │         │     Sale     │
│──────────────│         │──────────────│
│ id (PK)      │         │ id (PK)      │
│ name         │         │ invoice_no   │
│ category_id  │         │ date         │
│ unit_price   │         │ subtotal     │
│ created_at   │         │ vat_rate     │
│ updated_at   │         │ vat_amount   │
└──────────────┘         │ discount_*   │
        │                │ total        │
        │                └──────────────┘
        │                        │
        │                        │ 1:N
        │                        │
        │                        ▼
        │                ┌──────────────┐
        └───────────────►│  SaleItem    │
                         │──────────────│
                         │ id (PK)      │
                         │ sale_id (FK) │
                         │ product_id   │
                         │ quantity     │
                         │ unit_price   │
                         │ total_price  │
                         └──────────────┘
```

## User Flow - Making a Sale

```
┌─────────────┐
│   START     │
└─────────────┘
      │
      ▼
┌─────────────────────────┐
│  User Opens POS Screen  │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Browse/Search Products │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Click Product to Add   │
│  to Cart                │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Adjust Quantities      │
│  (Optional)             │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Apply Discount         │
│  (Optional)             │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Review Totals:         │
│  • Subtotal             │
│  • Discount             │
│  • VAT (16%)            │
│  • Total                │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Click "Complete Sale"  │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Backend Processes:     │
│  1. Validate data       │
│  2. Calculate totals    │
│  3. Create Sale record  │
│  4. Create SaleItems    │
│  5. Generate invoice #  │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Display Invoice        │
└─────────────────────────┘
      │
      ▼
┌─────────────────────────┐
│  Print / Download PDF   │
│  (Optional)             │
└─────────────────────────┘
      │
      ▼
┌─────────────┐
│     END     │
└─────────────┘
```

## Request/Response Flow

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│ Browser  │         │  Django  │         │ Database │
└──────────┘         └──────────┘         └──────────┘
      │                    │                    │
      │  GET /pos/         │                    │
      │───────────────────►│                    │
      │                    │                    │
      │                    │  Query Products    │
      │                    │───────────────────►│
      │                    │                    │
      │                    │  Return Products   │
      │                    │◄───────────────────│
      │                    │                    │
      │  Render Template   │                    │
      │◄───────────────────│                    │
      │                    │                    │
      │  POST /pos/complete/                    │
      │───────────────────►│                    │
      │                    │                    │
      │                    │  Create Sale       │
      │                    │───────────────────►│
      │                    │                    │
      │                    │  Create SaleItems  │
      │                    │───────────────────►│
      │                    │                    │
      │                    │  Return Success    │
      │                    │◄───────────────────│
      │                    │                    │
      │  Redirect to Invoice                    │
      │◄───────────────────│                    │
      │                    │                    │
```

## Component Interaction

```
┌─────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  Navbar    │  │  Messages  │  │  Content   │            │
│  │  (base)    │  │  (alerts)  │  │  (pages)   │            │
│  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      URL ROUTING                             │
│  pos_system/urls.py  ──►  pos/urls.py                       │
│  /                    ──►  dashboard                         │
│  /products/           ──►  product_list                      │
│  /pos/                ──►  pos_screen                        │
│  /reports/sales/      ──►  sales_report                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                         VIEWS                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Product    │  │     POS      │  │   Reports    │      │
│  │   Views      │  │    Views     │  │    Views     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                        MODELS                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Category   │  │   Product    │  │     Sale     │      │
│  │              │  │              │  │   SaleItem   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       DATABASE                               │
│  Tables: pos_category, pos_product, pos_sale, pos_saleitem  │
└─────────────────────────────────────────────────────────────┘
```

## Calculation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SALE CALCULATION                          │
└─────────────────────────────────────────────────────────────┘

Step 1: Calculate Subtotal
┌──────────────────────────────────────┐
│ Subtotal = Σ(quantity × unit_price)  │
│                                      │
│ Example:                             │
│ Item 1: 2 × 100 = 200               │
│ Item 2: 3 × 50  = 150               │
│ Subtotal = 350                       │
└──────────────────────────────────────┘
                │
                ▼
Step 2: Apply Discount
┌──────────────────────────────────────┐
│ If percentage:                       │
│   Discount = Subtotal × (value/100)  │
│ If fixed:                            │
│   Discount = value                   │
│                                      │
│ Example (10% discount):              │
│ Discount = 350 × 0.10 = 35          │
│ After Discount = 350 - 35 = 315     │
└──────────────────────────────────────┘
                │
                ▼
Step 3: Calculate VAT
┌──────────────────────────────────────┐
│ VAT = After_Discount × (rate/100)    │
│                                      │
│ Example (16% VAT):                   │
│ VAT = 315 × 0.16 = 50.40            │
└──────────────────────────────────────┘
                │
                ▼
Step 4: Calculate Total
┌──────────────────────────────────────┐
│ Total = After_Discount + VAT         │
│                                      │
│ Example:                             │
│ Total = 315 + 50.40 = 365.40        │
└──────────────────────────────────────┘
```

## File Structure

```
pos_system/
│
├── pos/                          # Main application
│   ├── migrations/               # Database migrations
│   ├── management/               # Custom commands
│   │   └── commands/
│   │       ├── seed_data.py     # Sample data
│   │       └── reset_admin.py   # Admin reset
│   ├── templates/pos/            # HTML templates
│   │   ├── base.html            # Base layout
│   │   ├── dashboard.html       # Dashboard
│   │   ├── pos_screen.html      # POS interface
│   │   ├── invoice.html         # Invoice view
│   │   ├── product_*.html       # Product pages
│   │   ├── category_*.html      # Category pages
│   │   └── sales_report.html    # Reports
│   ├── models.py                 # Data models
│   ├── views.py                  # Business logic
│   ├── urls.py                   # URL routing
│   └── admin.py                  # Admin config
│
├── pos_system/                   # Project config
│   ├── settings.py              # Settings
│   ├── urls.py                  # Main URLs
│   └── wsgi.py                  # WSGI
│
├── Documentation/
│   ├── README.md                # Main docs
│   ├── QUICKSTART.md            # Quick start
│   ├── DEPLOYMENT.md            # Deployment
│   ├── PROJECT_STRUCTURE.md     # Structure
│   ├── FUTURE_ENHANCEMENTS.md   # Extensions
│   ├── SYSTEM_OVERVIEW.md       # Overview
│   ├── ARCHITECTURE.md          # This file
│   └── CHANGELOG.md             # Changes
│
├── Setup/
│   ├── setup.bat                # Windows setup
│   ├── setup.sh                 # Linux setup
│   ├── requirements.txt         # Dependencies
│   └── .env.example             # Config template
│
└── manage.py                     # Django CLI
```

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                                │
│  • HTML5                                                     │
│  • CSS3 (Bootstrap 5)                                        │
│  • JavaScript (Vanilla)                                      │
│  • Bootstrap Icons                                           │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND                                 │
│  • Python 3.8+                                               │
│  • Django 4.2.7                                              │
│  • Django ORM                                                │
│  • Django Templates                                          │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      DATABASE                                │
│  • SQLite (Development)                                      │
│  • PostgreSQL (Production)                                   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      LIBRARIES                               │
│  • ReportLab (PDF generation)                                │
│  • python-decouple (Environment variables)                   │
│  • psycopg2 (PostgreSQL adapter)                             │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION SETUP                          │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐
│   Internet   │
└──────────────┘
       │
       ▼
┌──────────────┐
│  Nginx/      │  ◄── Reverse Proxy
│  Apache      │      SSL/TLS
└──────────────┘      Static Files
       │
       ▼
┌──────────────┐
│  Gunicorn/   │  ◄── WSGI Server
│  uWSGI       │      Application Server
└──────────────┘
       │
       ▼
┌──────────────┐
│   Django     │  ◄── Web Framework
│ Application  │      Business Logic
└──────────────┘
       │
       ▼
┌──────────────┐
│ PostgreSQL   │  ◄── Database
│   Database   │      Data Storage
└──────────────┘
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                           │
└─────────────────────────────────────────────────────────────┘

Layer 1: Network Security
┌──────────────────────────────────────┐
│ • HTTPS/SSL                          │
│ • Firewall                           │
│ • DDoS Protection                    │
└──────────────────────────────────────┘

Layer 2: Application Security
┌──────────────────────────────────────┐
│ • CSRF Protection                    │
│ • XSS Prevention                     │
│ • SQL Injection Prevention           │
│ • Secure Headers                     │
└──────────────────────────────────────┘

Layer 3: Authentication
┌──────────────────────────────────────┐
│ • Password Hashing (PBKDF2)          │
│ • Session Management                 │
│ • Admin Authentication               │
└──────────────────────────────────────┘

Layer 4: Data Security
┌──────────────────────────────────────┐
│ • Database Encryption                │
│ • Backup & Recovery                  │
│ • Access Control                     │
└──────────────────────────────────────┘
```

---

**Last Updated**: February 6, 2026
