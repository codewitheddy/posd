# Rate Limiting Implementation

This document describes the rate limiting implementation in the POS system to prevent brute force attacks.

## Overview

Rate limiting has been implemented using:
- **Django REST Framework Throttling** for API endpoints
- **django-ratelimit** for authentication views
- **Redis** (production) or **local memory cache** (development) for storage

## Configuration

### REST Framework Throttling

**Settings in `settings.py`:**
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'auth': '5/minute',
        'login': '3/minute',
    },
}
```

### Custom Throttle Classes

**File: `pos/throttling.py`**
- `AuthThrottle`: 5 requests per minute for general auth endpoints
- `LoginThrottle`: 3 requests per minute for login attempts

### Authentication Views Rate Limiting

**Decorators applied:**
- `login_view`: `@ratelimit(key='ip', rate='3/m', method='POST', block=True)`
- `password_reset_request`: `@ratelimit(key='ip', rate='2/m', method='POST', block=True)`
- `password_reset_confirm`: `@ratelimit(key='ip', rate='5/m', method='POST', block=True)`

### API Endpoints Rate Limiting

**Token Authentication:**
- `CustomTokenObtainPairView`: 3 requests per minute (login attempts)
- `CustomTokenRefreshView`: 5 requests per minute

**Sync Endpoints:**
- `sync_pull`: 10 requests per minute per user
- `sync_push`: 20 requests per minute per user

**General API:**
- Anonymous users: 100 requests per hour
- Authenticated users: 1000 requests per hour

## Cache Configuration

**Production (with Redis):**
```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        # ... Redis configuration
    }
}
```

**Development (fallback):**
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

## Security Benefits

1. **Brute Force Protection**: Login attempts limited to 3 per minute per IP
2. **Password Reset Protection**: Reset requests limited to prevent abuse
3. **API Abuse Prevention**: General rate limiting on all API endpoints
4. **Sync Protection**: Offline sync operations rate limited per user

## HTTP Response Codes

- **429 Too Many Requests**: Returned when rate limit exceeded
- **Blocked requests** show appropriate error messages

## Production Deployment Notes

1. **Use Redis**: Configure Redis for production deployments
2. **Monitor Rate Limits**: Log rate limit violations for security monitoring
3. **Adjust Limits**: Tune rate limits based on legitimate usage patterns
4. **IP-based Limiting**: Consider using more sophisticated key strategies (user + IP)

## Testing

Rate limiting can be tested by making repeated requests to protected endpoints:

```bash
# Test login rate limiting
for i in {1..5}; do
    curl -X POST -d "username=test&password=wrong" http://localhost:8000/login/
done

# Test API rate limiting
for i in {1..110}; do
    curl http://localhost:8000/api/v1/products/
done
```

## Dependencies

- `django-ratelimit>=4.1.0`
- `django-redis>=6.0.0` (for Redis support)
- `redis>=7.4.0` (for Redis support)