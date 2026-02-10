# POS System Architecture Diagrams

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     POS System Architecture                  │
│                    (Offline-First Hybrid)                    │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   Client Layer   │         │   Sync Layer     │         │  Server Layer    │
│                  │         │                  │         │                  │
│  ┌────────────┐  │         │  ┌────────────┐  │         │  ┌────────────┐  │
│  │  Browser   │  │◄───────►│  │   Sync     │  │◄───────►│  │   Django   │  │
│  │    UI      │  │         │  │  Manager   │  │         │  │  REST API  │  │
│  └────────────┘  │         │  └────────────┘  │         │  └────────────┘  │
│        ↕         │         │        ↕         │         │        ↕         │
│  ┌────────────┐  │         │  ┌────────────┐  │         │  ┌────────────┐  │
│  │  Service   │  │         │  │Background  │  │         │  │PostgreSQL/ │  │
│  │  Worker    │  │         │  │   Sync     │  │         │  │   MySQL    │  │
│  └────────────┘  │         │  └────────────┘  │         │  └────────────┘  │
│        ↕         │         │                  │         │                  │
│  ┌────────────┐  │         │                  │         │                  │
│  │ IndexedDB  │  │         │                  │         │                  │
│  │  (Local)   │  │         │                  │         │                  │
│  └────────────┘  │         │                  │         │                  │
└──────────────────┘         └──────────────────┘         └──────────────────┘
     Offline OK                Auto-Sync                    Cloud Database
```

## Data Flow - Online Mode

```
User Action (e.g., Create Sale)
        │
        ↓
┌───────────────────┐
│  1. Save to       │
│     IndexedDB     │  ← Instant (0-50ms)
│     (Local)       │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  2. Update UI     │  ← Immediate feedback
│     (Optimistic)  │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  3. API Call      │  ← Background (100-500ms)
│     to Server     │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  4. Save to       │
│     Cloud DB      │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  5. Confirm       │
│     Success       │
└───────────────────┘
```

## Data Flow - Offline Mode

```
User Action (e.g., Create Sale)
        │
        ↓
┌───────────────────┐
│  1. Save to       │
│     IndexedDB     │  ← Instant (0-50ms)
│     (Local)       │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  2. Add to        │
│     Sync Queue    │  ← Queued for later
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  3. Update UI     │  ← Immediate feedback
│     (Optimistic)  │
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  4. Wait for      │
│     Connection    │  ← Automatic detection
└───────────────────┘
        │
        ↓
┌───────────────────┐
│  5. Auto-Sync     │  ← When online
│     to Server     │
└───────────────────┘
```

## Sync Process

```
┌─────────────────────────────────────────────────────────────┐
│                    Bidirectional Sync                        │
└─────────────────────────────────────────────────────────────┘

PULL (Server → Client)
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Request    │         │   Server     │         │   Client     │
│   Updates    │────────►│   Checks     │────────►│   Updates    │
│   Since      │         │   Changes    │         │   Local DB   │
│   Last Sync  │         │   Since      │         │              │
└──────────────┘         └──────────────┘         └──────────────┘

PUSH (Client → Server)
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Get Local  │         │   Send to    │         │   Server     │
│   Changes    │────────►│   Server     │────────►│   Saves to   │
│   (Queue)    │         │   (Batch)    │         │   Database   │
└──────────────┘         └──────────────┘         └──────────────┘

CONFLICT RESOLUTION
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Detect     │         │   Apply      │         │   Notify     │
│   Conflicts  │────────►│   Strategy   │────────►│   User       │
│              │         │   (Rules)    │         │   (Optional) │
└──────────────┘         └──────────────┘         └──────────────┘
```

## Multi-Location Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Multi-Location Sync Architecture                │
└─────────────────────────────────────────────────────────────┘

Store 1                    Cloud Server                Store 2
┌──────────┐              ┌──────────┐              ┌──────────┐
│ Browser  │              │  Django  │              │ Browser  │
│   +      │◄────────────►│   API    │◄────────────►│   +      │
│IndexedDB │              │    +     │              │IndexedDB │
└──────────┘              │PostgreSQL│              └──────────┘
     ↕                    └──────────┘                   ↕
┌──────────┐                    ↕                   ┌──────────┐
│  Sync    │                    ↕                   │  Sync    │
│ Manager  │                    ↕                   │ Manager  │
└──────────┘                    ↕                   └──────────┘
                                ↕
                         ┌──────────┐
                         │  Store 3 │
                         │ Browser  │
                         │    +     │
                         │IndexedDB │
                         └──────────┘

All stores sync to central database
Real-time inventory updates
Centralized reporting
```

## Component Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      Component Stack                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Presentation Layer                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   HTML   │  │   CSS    │  │JavaScript│  │  Django  │   │
│  │Templates │  │  Styles  │  │   UI     │  │Templates │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Offline Layer                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Service  │  │IndexedDB │  │   Sync   │  │Background│   │
│  │ Worker   │  │ Storage  │  │ Manager  │  │  Sync    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  API Layer                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   REST   │  │   JWT    │  │  CORS    │  │  Swagger │   │
│  │   API    │  │  Auth    │  │ Headers  │  │   Docs   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Business Logic Layer                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Views   │  │  Models  │  │Serializers│ │Permissions│  │
│  │          │  │          │  │           │  │           │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Data Layer                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │PostgreSQL│  │  SQLite  │  │  Redis   │  │  Media   │   │
│  │  (Cloud) │  │  (Dev)   │  │ (Cache)  │  │  Files   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Authentication Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    JWT Authentication                        │
└─────────────────────────────────────────────────────────────┘

1. Login Request
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Client  │────────►│   API    │────────►│   Auth   │
│          │ POST    │ /token/  │ Verify  │  System  │
│          │ Creds   │          │ User    │          │
└──────────┘         └──────────┘         └──────────┘
                            │
                            ↓
2. Token Response
┌──────────┐         ┌──────────┐
│  Client  │◄────────│   API    │
│  Stores  │ Access  │  Returns │
│  Token   │ Token   │  Tokens  │
└──────────┘         └──────────┘

3. Authenticated Request
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Client  │────────►│   API    │────────►│ Validate │
│          │ Bearer  │ Endpoint │ Token   │  Token   │
│          │ Token   │          │         │          │
└──────────┘         └──────────┘         └──────────┘
                            │
                            ↓
4. Response
┌──────────┐         ┌──────────┐
│  Client  │◄────────│   API    │
│ Receives │  Data   │  Returns │
│  Data    │         │  Data    │
└──────────┘         └──────────┘

5. Token Refresh (when expired)
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Client  │────────►│   API    │────────►│   New    │
│          │ Refresh │/refresh/ │ Verify  │  Access  │
│          │ Token   │          │ Token   │  Token   │
└──────────┘         └──────────┘         └──────────┘
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Cloud Deployment (Production)               │
└─────────────────────────────────────────────────────────────┘

Internet
    │
    ↓
┌──────────────┐
│     CDN      │  ← Static files (CSS, JS, Images)
│  CloudFront  │
└──────────────┘
    │
    ↓
┌──────────────┐
│Load Balancer │  ← Distribute traffic
│     (ELB)    │
└──────────────┘
    │
    ├─────────────────┬─────────────────┐
    ↓                 ↓                 ↓
┌──────────┐    ┌──────────┐    ┌──────────┐
│  Django  │    │  Django  │    │  Django  │  ← App servers
│Instance 1│    │Instance 2│    │Instance 3│
└──────────┘    └──────────┘    └──────────┘
    │                 │                 │
    └─────────────────┴─────────────────┘
                      │
                      ↓
            ┌──────────────────┐
            │   PostgreSQL     │  ← Database
            │   (RDS/Managed)  │
            └──────────────────┘
                      │
                      ↓
            ┌──────────────────┐
            │      Redis       │  ← Cache/Queue
            │    (ElastiCache) │
            └──────────────────┘
                      │
                      ↓
            ┌──────────────────┐
            │       S3         │  ← Media storage
            │   (Object Store) │
            └──────────────────┘
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Security Layers                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Transport Security                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  HTTPS   │  │   SSL    │  │   TLS    │                  │
│  │  Only    │  │   Cert   │  │   1.3    │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Authentication Security                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │   JWT    │  │  Token   │  │  Refresh │                  │
│  │  Tokens  │  │  Expiry  │  │  Tokens  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Application Security                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │   CORS   │  │   CSRF   │  │   XSS    │                  │
│  │Protection│  │Protection│  │Protection│                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  Data Security                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │Encrypted │  │  Secure  │  │  Access  │                  │
│  │ Storage  │  │  Backup  │  │ Control  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Performance Optimization

```
┌─────────────────────────────────────────────────────────────┐
│                  Performance Strategy                        │
└─────────────────────────────────────────────────────────────┘

Client Side
┌──────────────┐
│   Service    │  ← Cache static assets
│   Worker     │  ← Offline capability
└──────────────┘
       ↓
┌──────────────┐
│  IndexedDB   │  ← Local data storage
│              │  ← Instant queries
└──────────────┘
       ↓
┌──────────────┐
│  Optimistic  │  ← Update UI immediately
│    Updates   │  ← Sync in background
└──────────────┘

Server Side
┌──────────────┐
│    Redis     │  ← Cache API responses
│    Cache     │  ← Session storage
└──────────────┘
       ↓
┌──────────────┐
│  Database    │  ← Indexed queries
│  Indexing    │  ← Connection pooling
└──────────────┘
       ↓
┌──────────────┐
│     CDN      │  ← Static file delivery
│              │  ← Global distribution
└──────────────┘
```

## Monitoring & Logging

```
┌─────────────────────────────────────────────────────────────┐
│                  Monitoring Architecture                     │
└─────────────────────────────────────────────────────────────┘

Application
    │
    ├──► Logs ──────────► CloudWatch/Papertrail
    │
    ├──► Metrics ───────► Prometheus/Grafana
    │
    ├──► Errors ────────► Sentry
    │
    ├──► Performance ───► New Relic/DataDog
    │
    └──► Uptime ────────► Pingdom/UptimeRobot

Database
    │
    ├──► Query Stats ───► pg_stat_statements
    │
    ├──► Slow Queries ──► Query logs
    │
    └──► Connections ───► Connection pool stats

Sync
    │
    ├──► Sync Status ───► Custom dashboard
    │
    ├──► Queue Size ────► Redis monitoring
    │
    └──► Conflicts ─────► Alert system
```

## Legend

```
Symbols Used:
─────  Connection/Flow
◄────► Bidirectional
  ↕    Up/Down flow
  ↓    Downward flow
  │    Vertical connection
┌───┐  Component box
```

## Notes

- All diagrams show logical architecture
- Physical deployment may vary by provider
- Arrows indicate data flow direction
- Boxes represent system components
- Layers show separation of concerns
