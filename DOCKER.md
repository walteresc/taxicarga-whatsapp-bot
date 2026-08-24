# Docker Setup for Taxi Carga CRM

## Architecture

```
┌─────────────────────────────────────────┐
│         Nginx (Port 8001)               │
│  ├─ Static files (/static/, assets)     │
│  ├─ SPA fallback (Vue Router)           │
│  └─ Proxy to Django                     │
└─────────────────┬───────────────────────┘
                  │
       ┌──────────┴──────────┐
       │                     │
    Django                 SSE
    (Gunicorn)         (Long-lived)
    Port 8000          No buffering
       │                     │
       └──────────┬──────────┘
                  │
     ┌────────────┼────────────┐
     │            │            │
  PostgreSQL   Redis       Health
  (Port 5432)  (Port 6379) Checks
```

## Quick Start

### Development (with auto-reload)

```bash
docker compose up --build
```

Access: http://localhost:8001/login

Services:
- Nginx: http://localhost:8001
- Django: http://localhost:8000 (not exposed via Nginx; use through reverse proxy)
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Environment Setup

```bash
cp .env.example .env
# Edit .env with your settings
```

## Services

### Nginx (Port 8001)
- Reverse proxy to Django
- Serves Vue build (staticfiles/)
- Handles SPA routing with fallback to index.html
- Proxies API, auth, SSE, webhooks
- Special handling for Server-Sent Events (no buffering)
- HMAC webhook preservation (raw body)

### Django/Gunicorn (Port 8000, internal only)
- Application server
- Worker pool: gthread (supports SSE)
- Connected to PostgreSQL
- Connected to Redis
- Migrations run on startup
- Static files collected on startup

### PostgreSQL (Port 5432)
- Database: taxicarga_pg_test
- User: taxicarga
- Persistent volume: postgres_data
- Healthcheck: pg_isready

### Redis (Port 6379)
- Event Streams for real-time messaging
- Persistent volume: redis_data
- Healthcheck: redis-cli ping

## Commands

### Build and start

```bash
docker compose up --build
```

### Start (no rebuild)

```bash
docker compose up
```

### Stop

```bash
docker compose down
```

### Remove all data

```bash
docker compose down -v
```

### View logs

```bash
docker compose logs -f django
docker compose logs -f nginx
docker compose logs -f postgres
```

### Run Django management command

```bash
docker compose exec django python manage.py <command>
```

Examples:
```bash
docker compose exec django python manage.py migrate
docker compose exec django python manage.py shell
docker compose exec django python manage.py createsuperuser
```

### Restart a service

```bash
docker compose restart django
```

### Access shell in service

```bash
docker compose exec django bash
docker compose exec postgres psql -U taxicarga -d taxicarga_pg_test
```

## Deployment Considerations

### For Production VPS

1. **Don't use docker-compose.yml directly** — use a deployment tool:
   - Docker Swarm
   - Kubernetes
   - AWS ECS
   - DigitalOcean App Platform

2. **Security hardening needed**:
   - Set DEBUG=False (already in docker-compose)
   - Generate real SECRET_KEY
   - Use real YCLOUD_WEBHOOK_SECRET
   - Enable SESSION_COOKIE_SECURE (HTTPS)
   - Enable CSRF_COOKIE_SECURE (HTTPS)
   - Set strong database password

3. **Reverse proxy in front**:
   - Cloudflare (recommended)
   - AWS CloudFront
   - Nginx on VPS

4. **Database backup**:
   - Use managed PostgreSQL (e.g., AWS RDS, DigitalOcean Database)
   - Or backup volumes regularly
   - Test restore procedure

5. **Monitoring**:
   - Health checks (Nginx, Django, PostgreSQL, Redis)
   - Logs aggregation (Papertrail, CloudWatch, ELK)
   - Metrics (Prometheus, DataDog)
   - Alerting on failures

### Environment Variables

Required:
- `DB_NAME`: PostgreSQL database name
- `DB_USER`: PostgreSQL user
- `DB_PASSWORD`: PostgreSQL password
- `YCLOUD_WEBHOOK_SECRET`: Your YCloud webhook secret

Optional:
- `DEBUG`: Set to "False" for production
- `SECRET_KEY`: Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `ALLOWED_HOSTS`: Comma-separated hostnames
- `REDIS_URL`: Redis connection string (default: redis://redis:6379/0)
- `SESSION_COOKIE_SECURE`: Set to "True" for HTTPS
- `CSRF_COOKIE_SECURE`: Set to "True" for HTTPS

## Testing

### All tests

```bash
docker compose exec django python manage.py test
```

### Django tests only

```bash
docker compose exec django python manage.py test apps.whatsapp.tests
```

### Check connectivity

```bash
# PostgreSQL
docker compose exec django python -c "from django.db import connection; print('DB:', connection.get_database_name())"

# Redis
docker compose exec django python -c "import redis; r = redis.Redis.from_url('redis://redis:6379/0'); print('Redis:', r.ping())"

# Nginx proxy
curl -I http://localhost:8001/health/live
```

## Troubleshooting

### Service won't start

```bash
# Check logs
docker compose logs django

# Restart everything
docker compose down
docker compose up --build
```

### Database connection refused

```bash
# Wait for PostgreSQL
docker compose logs postgres

# Check if healthy
docker compose ps postgres
```

### Nginx returning 502 Bad Gateway

```bash
# Check Django is healthy
docker compose logs django

# Check if Django is listening
docker compose exec nginx curl http://django:8000/health/live
```

### Clear Redis cache

```bash
docker compose exec redis redis-cli FLUSHALL
```

### Backup database

```bash
docker compose exec postgres pg_dump -U taxicarga taxicarga_pg_test > backup.sql
```

### Restore database

```bash
docker compose exec -T postgres psql -U taxicarga taxicarga_pg_test < backup.sql
```

## Architecture Notes

### Why Gunicorn + Nginx?

- **Gunicorn**: Stable Python app server, handles multiple workers/threads
- **Nginx**: Fast reverse proxy, better at serving static files, handles SSE properly
- **Separation**: Allows independent scaling, updates without downtime

### SSE Configuration

Nginx is configured specifically for SSE:
- `proxy_buffering off` — stream data immediately
- `proxy_cache off` — no caching
- `X-Accel-Buffering no` — tell backend not to buffer
- Long timeouts (300s) for persistent connections

### Webhook Handling

HMAC signature validation requires raw body:
- Nginx proxies `/webhooks/ycloud/v1/` without modification
- `proxy_pass_request_headers on` preserves signature headers
- Django validates signature on raw POST body

### Static Files

Nginx serves from `staticfiles/` directory (populated by `collectstatic`):
- Vue build: staticfiles/static/css/, staticfiles/static/js/
- Favicon, loader.css: staticfiles root
- Cache headers: 30 days for versioned assets

## Next Steps

1. **Test locally**: `docker compose up`
2. **Verify all services**: Check logs and health endpoints
3. **Plan VPS deployment**: Choose platform and backup strategy
4. **Set up Cloudflare**: DNS pointing to VPS
5. **Enable HTTPS**: Let's Encrypt or Cloudflare SSL

## Reference

- Docker Compose: https://docs.docker.com/compose/
- Gunicorn: https://docs.gunicorn.org/
- Nginx: https://nginx.org/
- PostgreSQL: https://www.postgresql.org/docs/
- Redis: https://redis.io/documentation
