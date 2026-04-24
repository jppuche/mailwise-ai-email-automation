# Infrastructure & DevOps Review -- mailwise

**Reviewer:** Sentinel (DevOps/Infra perspective)
**Date:** 2026-03-02
**Scope:** Docker Compose, Dockerfiles, health checks, structured logging, 12-factor compliance, deployment docs, .env.example
**Methodology:** Read actual files; findings grounded in concrete line references

---

## Executive Summary

The infrastructure layer is well above average for a portfolio project. Multi-stage Docker builds, health checks on all 6 services, structured JSON logging with PII redaction, fully externalized configuration via pydantic-settings, and a comprehensive deployment guide demonstrate serious production awareness. The 21 findings below are refinements, not rewrites -- the foundation is solid.

**Findings by severity:**
- CRITICAL: 2
- HIGH: 4
- MEDIUM: 8
- LOW: 7

---

## 1. Docker Compose

### Files reviewed

- `docker-compose.yml` (base, 128 lines)
- `docker-compose.dev.yml` (dev overrides, 23 lines)
- `docker-compose.prod.yml` (prod overrides, 34 lines)

### STRENGTH: Health check architecture

All 6 services have health checks with configurable intervals via env vars (`HEALTHCHECK_INTERVAL`, `HEALTHCHECK_TIMEOUT`, `HEALTHCHECK_RETRIES`, `HEALTHCHECK_START_PERIOD`). Dependency ordering uses `condition: service_healthy`, not just `depends_on` -- containers start only when their dependencies are confirmed healthy. This is correct and production-grade.

### STRENGTH: Dev/prod separation

Three-file overlay pattern (`base` + `dev` + `prod`) is the Docker Compose best practice. Dev adds volume mounts and `--reload`, prod adds `restart: unless-stopped` and JSON logging.

### FINDING-01: Database and Redis ports exposed to host in base compose

**Severity: CRITICAL**
**File:** `docker-compose.yml`, lines 10-11 (db) and lines 23-24 (redis)
**Detail:** `ports: "5432:5432"` and `ports: "6379:6379"` are in the **base** compose file, not the dev override. The prod override (`docker-compose.prod.yml`) does NOT remove these port mappings. The `deployment.md` line 236 claims "The prod override removes `ports:` exposure for `db` and `redis`" but this is factually incorrect -- the prod override file contains no `ports:` overrides at all.

In production, PostgreSQL and Redis would be directly accessible on the host network without authentication (Redis has no password configured anywhere).

**Suggested fix:**
Move `ports:` for `db` and `redis` from `docker-compose.yml` to `docker-compose.dev.yml`. The prod override should NOT expose these services to the host.

```yaml
# docker-compose.dev.yml — add:
  db:
    ports:
      - "5432:5432"
  redis:
    ports:
      - "6379:6379"
```

Remove the `ports:` sections from the base `docker-compose.yml` for `db` and `redis`.

### FINDING-02: Redis has no authentication

**Severity: CRITICAL**
**File:** `docker-compose.yml` line 21-34, `docker-compose.prod.yml` line 33
**Detail:** Redis runs with no password. Combined with FINDING-01, anyone on the network can connect to Redis and read JWT refresh tokens, Celery task payloads, classification cache, and scheduler lock state. The prod override adds `--appendonly yes` but no `--requirepass`.

**Suggested fix:**
Add a `REDIS_PASSWORD` env var. Update `docker-compose.yml`:
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD:-redis-dev-password}
```
Update `REDIS_URL` and `CELERY_BROKER_URL` to include the password: `redis://:${REDIS_PASSWORD}@redis:6379/0`.

### FINDING-03: No resource limits on any service

**Severity: HIGH**
**File:** All three compose files
**Detail:** No `deploy.resources.limits` (memory, CPU) on any service. A runaway Celery worker or LLM request could OOM the host, taking down all 6 services. For a portfolio project, this matters less in practice but demonstrates a gap in production awareness.

**Suggested fix:**
Add to `docker-compose.prod.yml`:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
  worker:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
  db:
    deploy:
      resources:
        limits:
          memory: 512M
```

### FINDING-04: No container security hardening

**Severity: MEDIUM**
**File:** All three compose files
**Detail:** No `read_only: true`, no `security_opt: [no-new-privileges:true]`, no `cap_drop: [ALL]` on any service. These are standard Docker security best practices that signal production awareness.

**Suggested fix:**
Add to `docker-compose.prod.yml` for each application service:
```yaml
  api:
    read_only: true
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
```

### FINDING-05: Frontend targets dev stage in base compose

**Severity: LOW**
**File:** `docker-compose.yml` line 105
**Detail:** `target: dev` is set in the base compose, and the prod override correctly changes it to `target: production`. This works but means `docker compose up` without specifying the prod override runs the Vite dev server in production-like environments.

**Suggested fix:** This is acceptable for a portfolio project where `docker compose up` is the default dev workflow. No change needed, but worth noting.

---

## 2. Dockerfiles

### Files reviewed

- `Dockerfile` (32 lines, backend)
- `Dockerfile.frontend` (31 lines, frontend)

### STRENGTH: Multi-stage build

Backend uses a proper 2-stage build (builder + runtime). Frontend uses a 3-stage build (dev + build + prod/nginx). Non-root `app` user is created in the backend runtime stage. The builder stage's pip cache and build tools are excluded from the final image.

### STRENGTH: CRLF fix in Dockerfile

`RUN sed -i 's/\r$//' ./docker/healthchecks/*.sh` (line 27) demonstrates awareness of cross-platform issues (Windows development, Linux containers). This was a real bug found and fixed per SCRATCHPAD line 100.

### FINDING-06: pip install -e . in builder stage creates mutable install

**Severity: HIGH**
**File:** `Dockerfile` line 10
**Detail:** `pip install -e .` creates an editable (development) install. In the runtime stage, the `mailwise.egg-info` directory is explicitly copied (line 23). Editable installs are fragile in multi-stage builds -- the `.egg-info/` symlinks back to the source. Since the source is also copied, it works, but it is an anti-pattern for production images. A non-editable install would be more robust.

**Suggested fix:**
```dockerfile
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .
```
Then remove the `COPY --from=builder /app/mailwise.egg-info ./mailwise.egg-info` line.

### FINDING-07: No .dockerignore for frontend context

**Severity: LOW**
**File:** `Dockerfile.frontend` line 9
**Detail:** `COPY frontend/ .` sends the entire `frontend/` directory including `node_modules/` (if present locally) into the build context. The root `.dockerignore` excludes `frontend/node_modules/` and `frontend/dist/`, which partially mitigates this. However, the `.dockerignore` relative path behavior depends on the build context being the project root (which it is -- `context: .` in compose). This works correctly as configured.

**Suggested fix:** No change needed -- `.dockerignore` correctly handles this.

### FINDING-08: No Alembic migration step on container startup

**Severity: HIGH**
**File:** `Dockerfile` line 31, `docker-compose.yml` line 37-56
**Detail:** The API container CMD is `uvicorn src.api.main:app`. Alembic files are copied into the image (`COPY alembic/ ./alembic/` and `COPY alembic.ini .`) but there is no `alembic upgrade head` step anywhere -- not in the Dockerfile, not in the compose command, and not in the FastAPI lifespan. The `deployment.md` line 36 mentions "runs Alembic migrations" but the code does not do this automatically.

If a new deployment has schema changes, migrations must be run manually (`docker compose exec api alembic upgrade head`). This is not documented in the deployment guide's quick-start section.

**Suggested fix:**
Either add an entrypoint script that runs migrations before starting uvicorn:
```bash
#!/bin/sh
alembic upgrade head
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```
Or document the manual step prominently in `deployment.md` Section 2 (Quick Start).

### FINDING-09: Frontend nginx stage has no custom config

**Severity: MEDIUM**
**File:** `Dockerfile.frontend` lines 28-31
**Detail:** The production nginx stage uses the default nginx config. For an SPA with client-side routing (React Router), nginx needs a `try_files $uri $uri/ /index.html;` directive to serve `index.html` for all routes. Without this, direct navigation to `/emails/123` returns a 404. No `nginx.conf` file exists in the project.

**Suggested fix:**
Create `frontend/nginx.conf`:
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api:8000;
    }
}
```
Add to `Dockerfile.frontend`:
```dockerfile
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
```

### FINDING-10: Frontend prod nginx runs as root

**Severity: MEDIUM**
**File:** `Dockerfile.frontend` lines 28-31
**Detail:** The `nginx:alpine` base image runs as root by default. The backend Dockerfile creates a non-root `app` user, but the frontend production stage does not. For consistency and security, nginx should run as a non-root user.

**Suggested fix:**
Use `nginxinc/nginx-unprivileged:alpine` as the base image, or add user configuration to the existing nginx stage.

---

## 3. Health Checks

### Files reviewed

- `docker/healthchecks/worker-health.sh` (7 lines)
- `docker/healthchecks/scheduler-health.sh` (8 lines)
- Health check directives in `docker-compose.yml`

### STRENGTH: Complete coverage

All 6 services have health checks:
- **db:** `pg_isready` (standard)
- **redis:** `redis-cli ping` (standard)
- **api:** Python `urllib.request.urlopen` to `/api/v1/health` (smart -- no curl/wget dependency needed)
- **worker:** `celery inspect ping` with hostname targeting
- **scheduler:** `/proc/1/cmdline` check (creative -- avoids needing `pgrep` in slim image)
- **frontend:** `wget --spider` (Alpine has wget built in)

### STRENGTH: API health check is deep

The `/api/v1/health` endpoint (`src/api/routers/health.py`) checks both PostgreSQL and Redis connectivity with configurable timeouts and returns latency metrics. It reports "degraded" vs "ok" vs "unavailable" per adapter. This is meaningfully above a simple `return 200`.

### FINDING-11: Worker health check is known-flaky

**Severity: MEDIUM**
**File:** `docker/healthchecks/worker-health.sh` line 6
**Detail:** `celery inspect ping` is known to be intermittently unreliable, as documented in SCRATCHPAD line 102: "Worker celery inspect ping healthcheck is flaky (intermittent pass/fail) but eventually stabilizes." The 3-retry + 15s timeout configuration helps, but the underlying mechanism is fragile under load.

**Suggested fix:**
Consider a file-based heartbeat: the worker writes a timestamp to `/tmp/celery-heartbeat` on each task completion, and the health check verifies the file is less than 60s old. Alternatively, use Celery's built-in `celery inspect active` which is more reliable than `ping`.

### FINDING-12: Scheduler health check only verifies PID 1 exists

**Severity: LOW**
**File:** `docker/healthchecks/scheduler-health.sh` line 8
**Detail:** `grep -qa "src.scheduler" /proc/1/cmdline` only confirms the scheduler process started. It does not verify the scheduler is actively scheduling (e.g., APScheduler could be in a crashed state with PID 1 still running). For a portfolio project, this is acceptable, but a deeper check would verify the scheduler's last successful job execution.

**Suggested fix:**
Have the scheduler job write a heartbeat timestamp to a file or Redis key, and check recency in the health script.

---

## 4. Structured Logging

### Files reviewed

- `src/core/logging.py` (121 lines)
- `src/core/correlation.py` (32 lines)

### STRENGTH: PII sanitization as last-line defense

The `_sanitize_pii` processor redacts 8 field names (`subject`, `from_address`, `body_plain`, `body_html`, `sender_name`, `recipient_address`, `sender_email`) from all log events. The docstring explicitly states this is the "safety net" -- primary PII prevention lives in services. This defense-in-depth approach aligns with D17.

### STRENGTH: Correlation ID via ContextVar

Using `contextvars.ContextVar` for correlation IDs is the correct async-safe approach. The default value `"no-correlation"` ensures logs are always parseable even without an active email context. This enables tracing a single email through all pipeline stages.

### STRENGTH: Dual renderer (JSON/text)

Production gets `JSONRenderer` (machine-parseable for log aggregators), development gets `ConsoleRenderer` (human-readable). Controlled via `LOG_FORMAT` env var. This is the correct pattern.

### FINDING-13: PII sanitizer only scans top-level keys

**Severity: MEDIUM**
**File:** `src/core/logging.py` lines 59-65
**Detail:** The comment on line 60 explicitly states "nested dicts are NOT traversed." If a developer accidentally logs `logger.info("event", details={"subject": "secret"})`, the nested `subject` would not be redacted. The docstring acknowledges this is intentional ("to minimize false positives"), and the primary defense is in the service layer. Acceptable as defense-in-depth, but worth documenting this limitation in the deployment guide.

**Suggested fix:**
Add a note to `deployment.md` Section 5 (Monitoring): "The PII filter only redacts top-level log keys. Nested structures are not traversed. Developers must avoid passing PII in nested dicts."

### FINDING-14: No request-level correlation ID injection

**Severity: MEDIUM**
**File:** `src/api/main.py`, `src/core/correlation.py`
**Detail:** The correlation ID system (`set_email_correlation_id`) is designed for the pipeline (Celery tasks), not for API requests. HTTP requests to the API do not get a correlation ID assigned. There is no middleware that generates or reads an `X-Request-ID` / `X-Correlation-ID` header. This means API request logs (authentication, CRUD operations, health checks) all share the default `"no-correlation"` value, making them impossible to trace individually.

**Suggested fix:**
Add a FastAPI middleware that generates a UUID for each request and calls `set_email_correlation_id()` (or a new `set_request_correlation_id()`). Optionally read an incoming `X-Request-ID` header for distributed tracing.

### FINDING-15: No log rotation or size limits

**Severity: LOW**
**File:** `src/core/logging.py` line 106-110
**Detail:** `logging.basicConfig(format="%(message)s", ...)` writes to stderr with no rotation. In Docker, this is typically acceptable because Docker's logging driver handles rotation (default `json-file` with `max-size` and `max-file`). However, the compose files do not configure Docker logging driver options.

**Suggested fix:**
Add to `docker-compose.prod.yml`:
```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"

services:
  api:
    logging: *default-logging
```

---

## 5. 12-Factor Compliance

### File reviewed

- `src/core/config.py` (151 lines)

### STRENGTH: Comprehensive externalization

Every configurable value identified in D14 (Cat 8 load-bearing defaults) is externalized: LLM temperatures (0.1/0.7), polling interval (300s), max retries, backoff base, batch size (50), JWT TTL (15min), bcrypt rounds (12), body truncation (4000), snippet length (200). This is textbook 12-factor Config (Factor III).

### STRENGTH: pydantic-settings with Field descriptions

Each env var has a `Field(description=...)` that serves as inline documentation. Required fields use `Field(...)` (no default), causing clear `ValidationError` on startup if missing. Optional fields have sensible defaults.

### STRENGTH: Fail-fast on missing config

`database_url`, `database_url_sync`, and `jwt_secret_key` are marked `Field(...)` (required). The application will not start without them. This is the correct approach -- fail loudly at startup, not at first request.

### FINDING-16: get_settings() creates a new Settings instance on every call

**Severity: HIGH**
**File:** `src/core/config.py` lines 149-150
**Detail:** `get_settings()` returns `Settings()` -- a new instance every time. `pydantic-settings` reads `.env` from disk and parses all fields on each instantiation. This function is called in `database.py` at module level (line 43, 57), in `celery_app.py`, in the scheduler, in health checks, and potentially on every request through DI. While Python and OS caching mitigate the disk I/O, it is wasteful and non-idiomatic.

**Suggested fix:**
Use `@lru_cache` (standard pattern for FastAPI settings):
```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```
This is the pattern recommended in the official FastAPI documentation.

### FINDING-17: Database connection pool not sized

**Severity: MEDIUM**
**File:** `src/core/database.py` lines 44-48, 57-61
**Detail:** Both `create_async_engine` and `create_engine` use default pool settings (SQLAlchemy default: `pool_size=5`, `max_overflow=10`). With Celery workers (each running multiple threads) and the API server, the total connection count could exceed PostgreSQL's default `max_connections=100`. No env var controls pool sizing.

**Suggested fix:**
Add `db_pool_size` and `db_max_overflow` to Settings, and pass them to both engine factories.

---

## 6. Deployment Guide

### File reviewed

- `docs/deployment.md` (300 lines)

### STRENGTH: Complete troubleshooting table

The troubleshooting section (Section 6) maps 10 specific symptoms to likely causes and solutions. This is unusually thorough for a portfolio project and demonstrates real operational experience (e.g., "bcrypt ImportError" from passlib incompatibility, "classification stuck in FETCHED" from missing LLM key).

### STRENGTH: Admin creation documented honestly

Section 4.1 states "No CLI module exists. Use the Python REPL inside the running api container" and provides a working code snippet. This is honest documentation -- it does not pretend a feature exists that does not.

### FINDING-18: deployment.md claims prod removes db/redis ports -- it does not

**Severity: HIGH (documentation accuracy)**
**File:** `docs/deployment.md` line 236
**Detail:** "The prod override removes ports: exposure for db and redis" -- this is false. `docker-compose.prod.yml` has no port overrides. See FINDING-01. This is a documentation-to-code mismatch that would mislead a deployer.

**Suggested fix:**
Either implement the port removal in `docker-compose.prod.yml` (preferred -- see FINDING-01), or update the documentation to state: "The base compose exposes db and redis ports for development. In production, remove these port mappings or use a firewall to restrict access."

### FINDING-19: No HTTPS/TLS termination guidance

**Severity: LOW**
**File:** `docs/deployment.md` lines 239-240
**Detail:** Section 5 mentions "Deploy behind a reverse proxy (Nginx, Caddy, Traefik)" but provides no configuration example. For a portfolio project that a reviewer might actually deploy, a minimal Caddy/Traefik compose example would be valuable.

**Suggested fix:**
Add a minimal Caddy example:
```yaml
  caddy:
    image: caddy:2-alpine
    ports:
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
```

---

## 7. .env.example

### File reviewed

- `.env.example` (205 lines)

### STRENGTH: Exhaustive coverage with Cat 8 annotations

Every field from `Settings` has a corresponding line in `.env.example` with default value, range guidance ("Too low: ..., Too high: ..."), and section grouping. The Cat 8 annotations (load-bearing defaults) are carried through from the architecture directives to the actual configuration file. 60+ variables organized into 15 sections.

### STRENGTH: Security guidance inline

Line 24: `JWT_SECRET_KEY=change-me-in-production-use-openssl-rand-hex-32` -- the default value itself is a reminder.
Line 35: `CORS_ORIGINS` notes "REQUIRED in production -- no safe default."

### FINDING-20: JWT_SECRET_KEY has a working default value

**Severity: MEDIUM**
**File:** `.env.example` line 24
**Detail:** `JWT_SECRET_KEY=change-me-in-production-use-openssl-rand-hex-32` is a valid string that will pass pydantic validation. If a user copies `.env.example` to `.env` without editing, the application will start with a predictable JWT secret. The `config.py` marks it as `Field(...)` (required, no default), so the `.env.example` value becomes the actual secret.

**Suggested fix:**
Either remove the value from `.env.example` (leave it as `JWT_SECRET_KEY=` to force the user to set it), or add a startup validation in `Settings` that rejects known-insecure values:
```python
@model_validator(mode="after")
def _reject_insecure_jwt_secret(self) -> "Settings":
    if "change-me" in self.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY must be changed from its default value")
    return self
```

### FINDING-21: ROUTING_DASHBOARD_BASE_URL port mismatch

**Severity: LOW**
**File:** `.env.example` line 139
**Detail:** `ROUTING_DASHBOARD_BASE_URL=http://localhost:3000` but the frontend runs on port 5173 (Vite dev) or 80 (nginx prod). Port 3000 is not used anywhere in the compose setup.

**Suggested fix:**
Change to `http://localhost:5173` for dev consistency, or document that this should point to the actual frontend URL.

---

## Summary Table

| ID | Area | Severity | Summary |
|----|------|----------|---------|
| F-01 | Compose | CRITICAL | db/redis ports exposed in base, not removed in prod |
| F-02 | Compose | CRITICAL | Redis has no authentication |
| F-03 | Compose | HIGH | No resource limits on any service |
| F-04 | Compose | MEDIUM | No container security hardening (read_only, no-new-privileges) |
| F-05 | Compose | LOW | Frontend targets dev in base |
| F-06 | Dockerfile | HIGH | Editable pip install in builder |
| F-07 | Dockerfile | LOW | Frontend .dockerignore coverage (mitigated) |
| F-08 | Dockerfile | HIGH | No automatic Alembic migration on startup |
| F-09 | Dockerfile | MEDIUM | Nginx SPA config missing (try_files) |
| F-10 | Dockerfile | MEDIUM | Nginx prod stage runs as root |
| F-11 | Health | MEDIUM | Worker celery inspect ping is flaky |
| F-12 | Health | LOW | Scheduler health only checks PID |
| F-13 | Logging | MEDIUM | PII sanitizer skips nested keys |
| F-14 | Logging | MEDIUM | No request-level correlation ID for API calls |
| F-15 | Logging | LOW | No Docker log rotation configured |
| F-16 | Config | HIGH | get_settings() re-instantiates on every call |
| F-17 | Config | MEDIUM | DB connection pool not configurable |
| F-18 | Deployment | HIGH | Docs claim prod removes ports -- it does not |
| F-19 | Deployment | LOW | No HTTPS/TLS config example |
| F-20 | .env | MEDIUM | JWT_SECRET_KEY has usable default |
| F-21 | .env | LOW | Dashboard URL port mismatch (3000 vs 5173) |

---

## Overall Assessment

**Grade: B+**

For a portfolio project, this infrastructure is strong. The presence of health checks on all 6 services, defense-in-depth PII logging, fully externalized Cat 8 defaults, and honest deployment documentation put it well above the typical portfolio threshold.

The two CRITICAL findings (exposed ports + unauthenticated Redis) and the documentation mismatch (F-18) are the items that would catch a DevOps reviewer's eye. The remaining findings are refinements that demonstrate deeper production knowledge but are not blocking for a portfolio demonstration.

**Top 3 fixes for maximum portfolio impact (minimal effort, maximum signal):**
1. Move db/redis ports to dev override + add Redis password (F-01 + F-02) -- 10 minutes
2. Add `@lru_cache` to `get_settings()` (F-16) -- 1 minute
3. Fix deployment.md port claim (F-18) -- 1 minute
