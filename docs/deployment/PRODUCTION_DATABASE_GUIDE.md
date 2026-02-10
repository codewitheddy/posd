# Production Database Guide - High-Performance POS System

## Recommended Database: PostgreSQL

For production with **thousands of products** and **high request volumes**, **PostgreSQL** is the best choice.

## Why PostgreSQL?

### ✅ Performance at Scale
- **Handles millions of rows** efficiently
- **Concurrent connections** - 100+ simultaneous users
- **Advanced indexing** - B-tree, Hash, GiST, GIN indexes
- **Query optimization** - Excellent query planner
- **Parallel queries** - Utilizes multiple CPU cores

### ✅ Data Integrity
- **ACID compliant** - No data loss
- **Foreign key constraints** - Referential integrity
- **Transactions** - Atomic operations
- **Point-in-time recovery** - Restore to any moment
- **Write-ahead logging** - Crash recovery

### ✅ Advanced Features
- **JSON/JSONB support** - Store flexible data
- **Full-text search** - Fast product search
- **Partitioning** - Split large tables
- **Materialized views** - Pre-computed reports
- **Extensions** - pg_stat_statements, pg_trgm

### ✅ Scalability
- **Vertical scaling** - Add more CPU/RAM
- **Read replicas** - Distribute read load
- **Connection pooling** - Handle more connections
- **Table partitioning** - Manage large datasets

### ✅ Cost-Effective
- **Open source** - No licensing fees
- **Managed services** - AWS RDS, Azure, DigitalOcean
- **Efficient storage** - TOAST for large data
- **Lower hardware requirements** - Optimized performance

## Performance Comparison

### PostgreSQL vs SQLite (Your Current DB)

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| **Max Database Size** | 281 TB | Unlimited |
| **Concurrent Writes** | 1 | Unlimited |
| **Concurrent Reads** | Unlimited | Unlimited |
| **Max Connections** | 1 | 1000+ |
| **Transactions** | Yes | Yes (Better) |
| **Replication** | No | Yes |
| **Partitioning** | No | Yes |
| **Full-Text Search** | Basic | Advanced |
| **JSON Support** | Basic | Advanced (JSONB) |
| **Best For** | Development | Production |

### PostgreSQL vs MySQL

| Feature | MySQL | PostgreSQL |
|---------|-------|------------|
| **ACID Compliance** | Partial | Full |
| **Complex Queries** | Good | Excellent |
| **JSON Support** | Good | Better (JSONB) |
| **Full-Text Search** | Good | Better |
| **Concurrency** | Good | Better (MVCC) |
| **Standards Compliance** | Partial | Full |
| **Extensions** | Limited | Extensive |
| **Best For** | Web apps | Complex apps |

## Recommended Configuration

### For Small-Medium Stores (1-5 locations)
```
Database: PostgreSQL 15+
CPU: 2-4 cores
RAM: 4-8 GB
Storage: 50-100 GB SSD
Connections: 100
Cost: $15-50/month
```

### For Large Stores (5-20 locations)
```
Database: PostgreSQL 15+
CPU: 4-8 cores
RAM: 16-32 GB
Storage: 200-500 GB SSD
Connections: 200
Cost: $100-300/month
```

### For Enterprise (20+ locations)
```
Database: PostgreSQL 15+
CPU: 8-16 cores
RAM: 64-128 GB
Storage: 1-2 TB SSD
Connections: 500+
Read Replicas: 2-3
Cost: $500-1500/month
```

## Setup Instructions

### 1. Update Django Settings

Create a production settings file:

```python
# pos_system/settings_production.py

import os
from .settings import *

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'pos_production'),
        'USER': os.getenv('DB_USER', 'pos_user'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling (10 minutes)
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000',  # 30 second timeout
        },
    }
}

# Connection Pooling (for high traffic)
DATABASES['default']['CONN_MAX_AGE'] = 600

# Cache Configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'pos',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# Session Storage (Redis for better performance)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Security Settings
DEBUG = False
ALLOWED_HOSTS = [os.getenv('DOMAIN', 'yourdomain.com')]
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Static Files (Use CDN in production)
STATIC_URL = os.getenv('STATIC_URL', '/static/')
MEDIA_URL = os.getenv('MEDIA_URL', '/media/')

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/pos/django.log',
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['file'],
            'level': 'WARNING',  # Log slow queries
            'propagate': False,
        },
    },
}
```

### 2. Database Optimization Settings

Create `postgresql.conf` optimizations:

```ini
# Memory Settings (for 16GB RAM server)
shared_buffers = 4GB                    # 25% of RAM
effective_cache_size = 12GB             # 75% of RAM
maintenance_work_mem = 1GB              # For VACUUM, CREATE INDEX
work_mem = 64MB                         # Per operation

# Checkpoint Settings
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100

# Query Planner
random_page_cost = 1.1                  # For SSD
effective_io_concurrency = 200          # For SSD

# Connection Settings
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# Logging (for monitoring)
log_min_duration_statement = 1000       # Log queries > 1 second
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
```

### 3. Essential Database Indexes

Create indexes for better performance:

```python
# pos/migrations/0011_add_performance_indexes.py

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('pos', '0010_customer_lifetime_points_customer_tier_and_more'),
    ]

    operations = [
        # Product indexes
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_product_barcode ON pos_product(barcode) WHERE barcode IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_product_barcode;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_product_code ON pos_product(product_code) WHERE product_code IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_product_code;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_product_active ON pos_product(is_active) WHERE is_active = true;",
            reverse_sql="DROP INDEX IF EXISTS idx_product_active;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_product_low_stock ON pos_product(stock_quantity, low_stock_threshold) WHERE stock_quantity <= low_stock_threshold;",
            reverse_sql="DROP INDEX IF EXISTS idx_product_low_stock;"
        ),
        
        # Sale indexes
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_sale_created ON pos_sale(created_at DESC);",
            reverse_sql="DROP INDEX IF EXISTS idx_sale_created;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_sale_customer ON pos_sale(customer_id) WHERE customer_id IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_sale_customer;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_sale_cashier ON pos_sale(cashier_id) WHERE cashier_id IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_sale_cashier;"
        ),
        
        # Customer indexes
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_customer_phone ON pos_customer(phone) WHERE phone IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_customer_phone;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_customer_email ON pos_customer(email) WHERE email IS NOT NULL;",
            reverse_sql="DROP INDEX IF EXISTS idx_customer_email;"
        ),
        
        # Full-text search index for products
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_product_name_trgm ON pos_product USING gin(name gin_trgm_ops);",
            reverse_sql="DROP INDEX IF EXISTS idx_product_name_trgm;"
        ),
    ]
```

### 4. Enable PostgreSQL Extensions

```sql
-- Connect to your database and run:

-- For full-text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- For query statistics
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- For UUID support (if needed)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

## Managed PostgreSQL Services

### 1. AWS RDS PostgreSQL (Recommended)
**Pros:**
- Automatic backups (35 days retention)
- Read replicas for scaling
- Multi-AZ for high availability
- Automated patching
- CloudWatch monitoring

**Pricing:**
- db.t3.medium (2 vCPU, 4GB): ~$60/month
- db.t3.large (2 vCPU, 8GB): ~$120/month
- db.m5.large (2 vCPU, 8GB): ~$140/month
- db.m5.xlarge (4 vCPU, 16GB): ~$280/month

**Setup:**
```bash
# Install AWS CLI
pip install awscli

# Create RDS instance
aws rds create-db-instance \
    --db-instance-identifier pos-production \
    --db-instance-class db.t3.medium \
    --engine postgres \
    --engine-version 15.4 \
    --master-username pos_admin \
    --master-user-password YOUR_PASSWORD \
    --allocated-storage 100 \
    --storage-type gp3 \
    --backup-retention-period 7 \
    --multi-az
```

### 2. DigitalOcean Managed PostgreSQL
**Pros:**
- Simple pricing
- Automatic backups
- Easy scaling
- Good performance
- Excellent support

**Pricing:**
- Basic (1 vCPU, 1GB): $15/month
- Basic (1 vCPU, 2GB): $30/month
- Basic (2 vCPU, 4GB): $60/month
- Professional (4 vCPU, 8GB): $120/month

**Setup:**
```bash
# Install doctl
brew install doctl  # or download from DigitalOcean

# Create database
doctl databases create pos-production \
    --engine pg \
    --version 15 \
    --size db-s-2vcpu-4gb \
    --region nyc1
```

### 3. Azure Database for PostgreSQL
**Pros:**
- Enterprise features
- Global availability
- Azure integration
- Advanced security

**Pricing:**
- Basic (1 vCPU, 2GB): ~$30/month
- General Purpose (2 vCPU, 8GB): ~$150/month
- Memory Optimized (4 vCPU, 32GB): ~$400/month

### 4. Google Cloud SQL for PostgreSQL
**Pros:**
- Google infrastructure
- Automatic scaling
- High availability
- Good pricing

**Pricing:**
- db-f1-micro (0.6GB): ~$10/month
- db-g1-small (1.7GB): ~$25/month
- db-n1-standard-1 (3.75GB): ~$50/month
- db-n1-standard-2 (7.5GB): ~$100/month

### 5. Heroku PostgreSQL
**Pros:**
- Easiest setup
- Integrated with Heroku
- Automatic backups
- Simple pricing

**Pricing:**
- Hobby Basic (10M rows): $9/month
- Standard 0 (64GB storage): $50/month
- Standard 2 (256GB storage): $200/month
- Premium 0 (512GB storage): $500/month

## Performance Optimization

### 1. Connection Pooling

Install PgBouncer:

```bash
# Ubuntu/Debian
sudo apt-get install pgbouncer

# Configure /etc/pgbouncer/pgbouncer.ini
[databases]
pos_production = host=localhost port=5432 dbname=pos_production

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
```

Update Django settings:
```python
DATABASES['default']['PORT'] = '6432'  # PgBouncer port
```

### 2. Query Optimization

```python
# Use select_related for foreign keys
products = Product.objects.select_related('category').all()

# Use prefetch_related for reverse foreign keys
sales = Sale.objects.prefetch_related('items', 'payments').all()

# Use only() to fetch specific fields
products = Product.objects.only('id', 'name', 'price').all()

# Use defer() to exclude fields
products = Product.objects.defer('description', 'image').all()

# Use values() for dictionaries (faster)
products = Product.objects.values('id', 'name', 'price')

# Use iterator() for large querysets
for product in Product.objects.iterator(chunk_size=1000):
    process(product)

# Use bulk operations
Product.objects.bulk_create([...])
Product.objects.bulk_update([...], ['price', 'stock_quantity'])
```

### 3. Caching Strategy

```python
# Cache expensive queries
from django.core.cache import cache

def get_dashboard_stats():
    stats = cache.get('dashboard_stats')
    if stats is None:
        stats = calculate_stats()
        cache.set('dashboard_stats', stats, 300)  # 5 minutes
    return stats

# Cache API responses
from rest_framework.decorators import action
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

class ProductViewSet(viewsets.ModelViewSet):
    @method_decorator(cache_page(60 * 5))  # 5 minutes
    @action(detail=False)
    def low_stock(self, request):
        # ...
```

### 4. Database Maintenance

```sql
-- Analyze tables (update statistics)
ANALYZE;

-- Vacuum (reclaim storage)
VACUUM ANALYZE;

-- Reindex (rebuild indexes)
REINDEX DATABASE pos_production;

-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check slow queries
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

## Monitoring

### 1. Enable Query Logging

```python
# settings_production.py

if DEBUG:
    LOGGING['loggers']['django.db.backends'] = {
        'handlers': ['console'],
        'level': 'DEBUG',
    }
```

### 2. Monitor with pg_stat_statements

```sql
-- Top 10 slowest queries
SELECT 
    substring(query, 1, 50) AS short_query,
    round(total_time::numeric, 2) AS total_time,
    calls,
    round(mean_time::numeric, 2) AS mean,
    round((100 * total_time / sum(total_time) OVER ())::numeric, 2) AS percentage
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;
```

### 3. Monitor Connections

```sql
-- Current connections
SELECT count(*) FROM pg_stat_activity;

-- Connections by state
SELECT state, count(*) 
FROM pg_stat_activity 
GROUP BY state;

-- Long-running queries
SELECT 
    pid,
    now() - query_start AS duration,
    query
FROM pg_stat_activity
WHERE state = 'active'
AND now() - query_start > interval '1 minute'
ORDER BY duration DESC;
```

## Backup Strategy

### Automated Backups

```bash
#!/bin/bash
# /usr/local/bin/backup-postgres.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"
DB_NAME="pos_production"

# Create backup
pg_dump -U pos_user -h localhost $DB_NAME | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete

# Upload to S3 (optional)
aws s3 cp $BACKUP_DIR/backup_$DATE.sql.gz s3://your-bucket/backups/
```

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-postgres.sh
```

## Migration from SQLite

```bash
# 1. Export data from SQLite
python manage.py dumpdata --natural-foreign --natural-primary > data.json

# 2. Update settings to use PostgreSQL
export DJANGO_SETTINGS_MODULE=pos_system.settings_production

# 3. Create PostgreSQL database
createdb pos_production

# 4. Run migrations
python manage.py migrate

# 5. Import data
python manage.py loaddata data.json

# 6. Verify data
python manage.py shell
>>> from pos.models import Product
>>> Product.objects.count()
```

## Conclusion

**For production with high traffic and large datasets, use PostgreSQL with:**

✅ **Managed service** (AWS RDS or DigitalOcean recommended)
✅ **Connection pooling** (PgBouncer)
✅ **Redis caching** (for API responses)
✅ **Proper indexes** (on frequently queried fields)
✅ **Regular maintenance** (VACUUM, ANALYZE)
✅ **Monitoring** (pg_stat_statements)
✅ **Automated backups** (daily)

**Expected Performance:**
- Handle 10,000+ products easily
- Support 100+ concurrent users
- Process 1000+ transactions/hour
- Sub-second query response times
- 99.9% uptime with managed services

**Recommended Starting Point:**
- **DigitalOcean Managed PostgreSQL** (2 vCPU, 4GB) - $60/month
- Simple setup, good performance, excellent support
- Easy to scale as you grow
