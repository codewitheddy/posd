# PostgreSQL Setup Guide

Complete guide for setting up PostgreSQL with your Django POS system.

## Why PostgreSQL?

PostgreSQL is recommended for production because:
- Better performance for complex queries
- Advanced features (JSON fields, full-text search)
- Better data integrity and ACID compliance
- Excellent scalability
- Free and open source

## Local Development Setup

### Windows

1. **Download PostgreSQL**
   - Visit: https://www.postgresql.org/download/windows/
   - Download PostgreSQL 15 or later
   - Run installer

2. **During Installation**
   - Remember the password you set for `postgres` user
   - Default port: 5432
   - Install pgAdmin 4 (GUI tool)

3. **Create Database**
   ```sql
   -- Open pgAdmin or psql
   CREATE DATABASE pos_db;
   CREATE USER pos_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
   
   -- PostgreSQL 15+ requires additional permissions
   \c pos_db
   GRANT ALL ON SCHEMA public TO pos_user;
   ```

4. **Update .env**
   ```env
   DATABASE_ENGINE=postgresql
   DATABASE_NAME=pos_db
   DATABASE_USER=pos_user
   DATABASE_PASSWORD=your_password
   DATABASE_HOST=localhost
   DATABASE_PORT=5432
   ```

5. **Install Python Package**
   ```bash
   pip install psycopg2-binary
   ```

6. **Run Migrations**
   ```bash
   python manage.py migrate
   ```

### Linux (Ubuntu/Debian)

```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql

# In psql:
CREATE DATABASE pos_db;
CREATE USER pos_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
\c pos_db
GRANT ALL ON SCHEMA public TO pos_user;
\q

# Install Python package
pip install psycopg2-binary

# Update .env and run migrations
python manage.py migrate
```

### macOS

```bash
# Install PostgreSQL using Homebrew
brew install postgresql@15

# Start PostgreSQL
brew services start postgresql@15

# Create database
createdb pos_db
psql pos_db

# In psql:
CREATE USER pos_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
GRANT ALL ON SCHEMA public TO pos_user;
\q

# Install Python package
pip install psycopg2-binary

# Update .env and run migrations
python manage.py migrate
```

## cPanel Deployment with PostgreSQL

### Step 1: Check PostgreSQL Availability

1. Login to cPanel
2. Look for **PostgreSQL Databases** or **PostgreSQL Database Wizard**
3. If not available, contact your hosting provider

### Step 2: Create PostgreSQL Database

1. Go to **PostgreSQL Databases**
2. Create new database: `youruser_posdb`
3. Create user: `youruser_posuser`
4. Set strong password
5. Add user to database with ALL PRIVILEGES

### Step 3: Get Connection Details

Note down:
- Database name: `youruser_posdb`
- Username: `youruser_posuser`
- Password: [your password]
- Host: `localhost` (or provided by host)
- Port: `5432` (default)

### Step 4: Update .env File

```env
DATABASE_ENGINE=postgresql
DATABASE_NAME=youruser_posdb
DATABASE_USER=youruser_posuser
DATABASE_PASSWORD=your_actual_password
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

### Step 5: Install psycopg2

```bash
# SSH into cPanel
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
pip install psycopg2-binary
```

### Step 6: Run Migrations

```bash
python manage.py migrate
```

## Cloud Hosting (Heroku, Render, Railway)

### Heroku

```bash
# Add PostgreSQL addon
heroku addons:create heroku-postgresql:mini

# Get DATABASE_URL
heroku config:get DATABASE_URL

# Migrations run automatically on deploy
git push heroku main
```

### Render

1. Create PostgreSQL database in Render dashboard
2. Copy Internal Database URL
3. Add as environment variable: `DATABASE_URL`
4. Deploy your app

### Railway

1. Add PostgreSQL plugin
2. Copy DATABASE_URL from variables
3. Add to environment variables
4. Deploy

## Database Management

### Using psql (Command Line)

```bash
# Connect to database
psql -U pos_user -d pos_db -h localhost

# Common commands
\dt                    # List tables
\d table_name         # Describe table
\l                    # List databases
\du                   # List users
\q                    # Quit

# Run SQL
SELECT * FROM pos_product LIMIT 10;
```

### Using pgAdmin (GUI)

1. Open pgAdmin
2. Right-click Servers → Create → Server
3. Name: POS Database
4. Connection tab:
   - Host: localhost
   - Port: 5432
   - Database: pos_db
   - Username: pos_user
   - Password: [your password]
5. Save

### Backup Database

```bash
# Using pg_dump
pg_dump -U pos_user -h localhost pos_db > backup.sql

# Using Django management command
python manage.py backup_database

# Restore from backup
psql -U pos_user -h localhost pos_db < backup.sql
```

### Database Optimization

```sql
-- Analyze tables for query optimization
ANALYZE;

-- Vacuum to reclaim storage
VACUUM;

-- Reindex for performance
REINDEX DATABASE pos_db;
```

## Troubleshooting

### Connection Refused

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list                # macOS

# Check if listening on port
sudo netstat -plnt | grep 5432
```

### Authentication Failed

1. Check password in .env
2. Verify user exists:
   ```sql
   \du
   ```
3. Check pg_hba.conf for authentication method

### Permission Denied

```sql
-- Grant all permissions
GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
\c pos_db
GRANT ALL ON SCHEMA public TO pos_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO pos_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO pos_user;
```

### Migrations Fail

```bash
# Check database connection
python manage.py dbshell

# If connection works, try:
python manage.py migrate --fake-initial

# Or reset migrations (CAUTION: loses data)
python manage.py migrate --run-syncdb
```

### Performance Issues

```sql
-- Check slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Add indexes
CREATE INDEX idx_product_name ON pos_product(name);
CREATE INDEX idx_sale_date ON pos_sale(date);
```

## PostgreSQL vs MySQL

| Feature | PostgreSQL | MySQL |
|---------|-----------|-------|
| Performance | Better for complex queries | Better for simple reads |
| Data Types | More advanced (JSON, Arrays) | Basic types |
| ACID Compliance | Full | Partial (InnoDB) |
| Full-text Search | Built-in | Limited |
| JSON Support | Excellent | Basic |
| Replication | Advanced | Good |
| Cost | Free | Free (Community) |

## Migration from SQLite/MySQL

### From SQLite

```bash
# Export data
python manage.py dumpdata > data.json

# Switch to PostgreSQL in .env
DATABASE_ENGINE=postgresql

# Create new database and migrate
python manage.py migrate

# Import data
python manage.py loaddata data.json
```

### From MySQL

```bash
# Install pgloader
sudo apt install pgloader  # Linux
brew install pgloader      # macOS

# Convert database
pgloader mysql://user:pass@localhost/mysql_db \
         postgresql://user:pass@localhost/pos_db
```

## Production Best Practices

1. **Connection Pooling**
   ```python
   # settings.py
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'CONN_MAX_AGE': 600,  # 10 minutes
       }
   }
   ```

2. **Regular Backups**
   ```bash
   # Daily backup cron job
   0 2 * * * pg_dump -U pos_user pos_db > /backups/pos_$(date +\%Y\%m\%d).sql
   ```

3. **Monitoring**
   - Use pg_stat_statements for query analysis
   - Monitor connection count
   - Track database size

4. **Security**
   - Use strong passwords
   - Limit network access
   - Regular security updates
   - SSL connections for remote access

## Quick Reference

```bash
# Install PostgreSQL client
pip install psycopg2-binary

# Create database
createdb pos_db

# Run migrations
python manage.py migrate

# Backup
pg_dump pos_db > backup.sql

# Restore
psql pos_db < backup.sql

# Connect
psql -U pos_user -d pos_db

# Check connection in Django
python manage.py dbshell
```

---

**PostgreSQL is now configured for your Django POS system!**
