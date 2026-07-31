# StandardSphere — EC2 Deployment Guide

**StandardSphere**  
Target: AWS EC2 (Amazon Linux 2023 or Ubuntu 22.04 LTS)  
Deployment model: Docker Compose on a single EC2 instance

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack](#2-tech-stack)
3. [EC2 Instance Requirements](#3-ec2-instance-requirements)
4. [EC2 Dependencies to Install](#4-ec2-dependencies-to-install)
5. [Repository Setup](#5-repository-setup)
6. [Environment Configuration](#6-environment-configuration)
7. [Production Docker Compose](#7-production-docker-compose)
8. [First-Time Deployment](#8-first-time-deployment)
9. [Database Migrations](#9-database-migrations)
10. [Seed the Admin User](#10-seed-the-admin-user)
11. [Nginx Reverse Proxy](#11-nginx-reverse-proxy)
12. [SSL / HTTPS (Certbot)](#12-ssl--https-certbot)
13. [Storage: Local vs S3](#13-storage-local-vs-s3)
14. [SMTP / Email Setup](#14-smtp--email-setup)
15. [Environment Variables Reference](#15-environment-variables-reference)
16. [Service Health Checks](#16-service-health-checks)
17. [Updating the Application](#17-updating-the-application)
18. [Logs](#18-logs)
19. [Security Checklist](#19-security-checklist)
20. [Ports Reference](#20-ports-reference)

---

## 1. Architecture Overview

```
Internet
   │
   ▼
Nginx (port 80/443)
   ├── /api/*      → FastAPI (ists_web  :8000)
   └── /*          → React SPA (served as static files built by Vite)

FastAPI (ists_web)
   ├── PostgreSQL 16  (ists_db  :5432)
   ├── Redis 7        (ists_redis :6379)
   └── /app/storage   (local file system) OR S3

Celery Worker  (ists_worker)  — queues: feeds, notifications, maintenance
Celery Beat    (ists_beat)    — DB-backed scheduler (celery_sqlalchemy_scheduler)

SMTP → external mail server (SES / SendGrid / etc.)
```

**Six Docker containers managed by Docker Compose:**

| Container | Image | Role |
|---|---|---|
| `ists_db` | `postgres:16-alpine` | Primary database |
| `ists_redis` | `redis:7-alpine` | Celery broker + result backend |
| `ists_web` | Built from `./backend` | FastAPI REST API |
| `ists_worker` | Same image as web | Celery worker (async tasks) |
| `ists_beat` | Same image as web | Celery Beat scheduler |
| `ists_frontend` | Static files via Nginx | React 19 SPA |

> **Note:** In production the React app is built into static files (`npm run build`) and served directly by Nginx. The `node:20-alpine` dev container is **not** used in production.

---

## 2. Tech Stack

### Backend

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.12 |
| API Framework | FastAPI | 0.111.x |
| ASGI Server | Uvicorn (with Gunicorn workers in prod) | 0.30.x |
| ORM | SQLAlchemy (async) | 2.0.x |
| Async DB driver | asyncpg | 0.29.x |
| Sync DB driver (Beat) | psycopg2-binary | 2.9.x |
| Migrations | Alembic | 1.13.x |
| Task queue | Celery | 5.4.x |
| Beat scheduler | celery-sqlalchemy-scheduler | 0.3.0 |
| Message broker | Redis | 7.x |
| RSS parsing | feedparser | 6.0.x |
| HTTP client | httpx + curl-cffi | 0.27.x / 0.15.x |
| Auth | python-jose (JWT) + passlib (bcrypt) | 3.3.x / 1.7.x |
| Email | aiosmtplib | 3.0.x |
| File type detection | python-magic (libmagic) | 0.4.x |
| Logging | structlog | 24.x |
| Rate limiting | slowapi | 0.1.x |
| Settings | pydantic-settings | 2.x |
| Package installer | uv | latest |

### Frontend

| Component | Technology | Version |
|---|---|---|
| Language | TypeScript | ~6.0 |
| Framework | React | 19.x |
| Build tool | Vite | 8.x |
| Routing | React Router | 7.x |
| Data fetching | TanStack Query | 5.x |
| HTTP client | Axios | 1.x |
| UI components | Radix UI (primitives) | various |
| Styling | Tailwind CSS | 3.4.x |
| Charts | Recharts | 3.x |
| Icons | Lucide React | latest |

### Infrastructure

| Component | Technology |
|---|---|
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| Container runtime | Docker 24+ |
| Orchestration | Docker Compose v2 |
| Reverse proxy | Nginx |
| SSL | Let's Encrypt via Certbot |
| Cloud | AWS EC2 |
| File storage | Local disk (default) or AWS S3 |

---

## 3. EC2 Instance Requirements

### Recommended instance size

| Environment | Instance type | vCPU | RAM | Storage |
|---|---|---|---|---|
| Staging / small team | `t3.medium` | 2 | 4 GB | 30 GB gp3 |
| Production (≤50 users) | `t3.large` | 2 | 8 GB | 50 GB gp3 |
| Production (50–200 users) | `t3.xlarge` | 4 | 16 GB | 100 GB gp3 |

### Operating system

- **Amazon Linux 2023** (recommended) — Docker available from official Amazon repos
- **Ubuntu 22.04 LTS** — also fully supported

### Security group inbound rules

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | Your office IP / VPN CIDR | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirects to HTTPS) |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

> Do **not** expose ports 5432, 6379, or 8000 directly to the internet.

---

## 4. EC2 Dependencies to Install

### Amazon Linux 2023

```bash
# ── System updates ──────────────────────────────────────
sudo dnf update -y

# ── Docker Engine ───────────────────────────────────────
sudo dnf install -y docker
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to the docker group (avoids sudo on every command)
sudo usermod -aG docker ec2-user
newgrp docker

# ── Docker Compose v2 (plugin) ──────────────────────────
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Verify
docker --version
docker compose version

# ── Git ─────────────────────────────────────────────────
sudo dnf install -y git

# ── Nginx ───────────────────────────────────────────────
sudo dnf install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# ── Certbot (Let's Encrypt) ─────────────────────────────
sudo dnf install -y python3-certbot-nginx

# ── Optional: Node.js (only needed if building frontend on the server) ──
# Skip this if you build the frontend in CI/CD and copy the dist/ folder
sudo dnf install -y nodejs npm
node --version   # should be 20.x or higher
```

### Ubuntu 22.04 LTS

```bash
# ── System updates ──────────────────────────────────────
sudo apt-get update && sudo apt-get upgrade -y

# ── Docker Engine ───────────────────────────────────────
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu
newgrp docker

# ── Git ─────────────────────────────────────────────────
sudo apt-get install -y git

# ── Nginx ───────────────────────────────────────────────
sudo apt-get install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# ── Certbot ─────────────────────────────────────────────
sudo apt-get install -y certbot python3-certbot-nginx

# ── Optional: Node.js 20 (for building frontend on server) ──
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

---

## 5. Repository Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/standards-version-control.git /opt/ists
cd /opt/ists

# Set ownership so your deploy user can manage the files
sudo chown -R $(whoami):$(whoami) /opt/ists
```

---

## 6. Environment Configuration

```bash
cd /opt/ists

# Copy the example env file
cp .env.example .env

# Edit with your real values
nano .env
```

**Minimum required changes for production:**

```dotenv
# --- Database ---
# Replace hostname "db" (Docker service name) with "db" — keep as-is for Compose networking
DATABASE_URL=postgresql+asyncpg://ists:STRONG_PASSWORD_HERE@db:5432/ists
DATABASE_SYNC_URL=postgresql+psycopg2://ists:STRONG_PASSWORD_HERE@db:5432/ists

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- Security ---
# MUST be changed from default. Generate a strong key:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=REPLACE_WITH_64_CHAR_HEX_STRING

# --- Storage ---
# Use "local" initially; switch to "s3" for scalable production
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/app/storage

# For S3 (optional):
# STORAGE_BACKEND=s3
# S3_BUCKET_NAME=ists-documents-prod
# AWS_REGION=ap-south-1
# AWS_ACCESS_KEY_ID=AKIAxxx
# AWS_SECRET_ACCESS_KEY=xxx

# --- SMTP ---
# Use SES, SendGrid, or any SMTP relay
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=AKIASMTP_USER
SMTP_PASSWORD=SMTP_PASSWORD
SMTP_USE_TLS=true
SMTP_FROM_ADDRESS=noreply@yourdomain.com

# --- CORS ---
# Set to your actual domain
CORS_ORIGINS=https://yourdomain.com

# --- Application ---
LOG_LEVEL=INFO
ENVIRONMENT=production

# --- RSS Feed API keys ---
# Fernet key encrypting api_keys.key_value at rest — generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# The actual rss2json.com API key(s) are managed via POST/PATCH /api-keys,
# not an env var — see scripts/backfill_api_keys.py to migrate off the old
# single-key setup, and add further keys once feed count nears 25/key.
API_KEY_ENCRYPTION_KEY=your_generated_fernet_key_here
```

---

## 7. Production Docker Compose

Create `/opt/ists/docker-compose.prod.yml`. This file:
- Removes dev bind-mounts (no hot-reload)
- Removes MailHog (use real SMTP)
- Hardens container settings

```yaml
# docker-compose.prod.yml — production overrides
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  db:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}   # read from .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    # Remove port exposure — only accessible within Docker network
    ports: []

  redis:
    # Remove port exposure
    ports: []

  web:
    command: >
      gunicorn app.main:app
      -k uvicorn.workers.UvicornWorker
      -w 2
      --bind 0.0.0.0:8000
      --timeout 60
      --access-logfile -
    volumes:
      - document_storage:/app/storage
    environment:
      ENVIRONMENT: production
      LOG_LEVEL: INFO
    # No bind-mount for source code in production
    # The image already contains the built source

  worker:
    volumes:
      - document_storage:/app/storage
    environment:
      ENVIRONMENT: production
      LOG_LEVEL: INFO

  beat:
    environment:
      ENVIRONMENT: production
      LOG_LEVEL: INFO

volumes:
  document_storage:
    name: ists_document_storage
```

> **Note:** Add `gunicorn` to `pyproject.toml` dependencies before building the production image:
> ```
> "gunicorn==22.*",
> ```

---

## 8. First-Time Deployment

```bash
cd /opt/ists

# 1. Build the backend image
docker compose build web

# 2. Start all services
docker compose up -d

# 3. Verify all containers are running
docker compose ps

# Expected output — all services should show "running" or "healthy":
# ists_db        running (healthy)
# ists_redis     running (healthy)
# ists_web       running
# ists_worker    running
# ists_beat      running
```

---

## 9. Database Migrations

Alembic migrations must be run once on first deploy and after every release that includes schema changes.

```bash
# Run all pending migrations
docker compose exec web python -m alembic upgrade head

# Check current migration version
docker compose exec web python -m alembic current

# View migration history
docker compose exec web python -m alembic history
```

**Current migrations (0001 → 0006):**

| Revision | Description |
|---|---|
| `0001` | Initial schema — users, standards, rss_feeds, history, notifications |
| `0002` | Add `content_hash` to standards (change detection) |
| `0003` | Add `document_uploaded` event type |
| `0004` | Add `system_config` table |
| `0005` | Add `stage_code`, `stage_name`, `published_date` to standards |
| `0006` | Add `parent_standard_id` (amendment parallel tracking) |

---

## 10. Seed the Admin User

Run once after migrations to create the initial admin account:

```bash
docker compose exec web python scripts/seed.py
```

**Default credentials (change immediately after first login):**

| Field | Value |
|---|---|
| Email | `admin@ists.local` |
| Password | `Admin1234!` |
| Role | `admin` |

---

## 11. Nginx Reverse Proxy

### Build the React frontend

```bash
cd /opt/ists/frontend

# Install dependencies
npm install

# Set your production API URL
echo "VITE_API_URL=https://yourdomain.com" > .env.production

# Build static files
npm run build
# Output goes to: /opt/ists/frontend/dist/
```

### Nginx site configuration

Create `/etc/nginx/conf.d/ists.conf`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect all HTTP to HTTPS (Certbot will fill this in)
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates — managed by Certbot
    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # Document uploads. Must exceed the app's MAX_UPLOAD_SIZE_MB (200) plus
    # multipart overhead — nginx returns its own 413 before FastAPI sees the
    # request, so raising MAX_UPLOAD_SIZE_MB alone has no effect.
    client_max_body_size 210M;

    # Large uploads over a slow link need longer than the 60s defaults.
    client_body_timeout 300s;
    proxy_read_timeout  300s;
    proxy_send_timeout  300s;

    # ── API — proxy to FastAPI ─────────────────────────────
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # ── WebSocket (optional — for future real-time features) ──
    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }

    # ── React SPA — serve static files ────────────────────
    root /opt/ists/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets aggressively
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

```bash
# Test and reload Nginx
sudo nginx -t
sudo systemctl reload nginx
```

### Alternative: S3 + CloudFront frontend hosting

If you host the frontend from an S3 bucket (with or without CloudFront) instead of Nginx, two things WILL break unless handled:

1. **MIME types.** S3 serves objects with the `Content-Type` stored at upload time — the default is `binary/octet-stream`, which browsers refuse to execute for ES module scripts (`Failed to load module script...`). Uploads must set `Content-Type` explicitly for `.js` (`text/javascript`) and `.css` (`text/css`), and CloudFront caches the header, so an invalidation is required after fixing it.
2. **API routing.** There is no Nginx in front of the SPA to proxy `/api/*`. Either add a CloudFront behavior routing `/api/*` to the EC2 origin, or build with `VITE_API_URL` pointing at the backend's own domain (and set `CORS_ORIGINS` accordingly). Production builds now **fail** if `VITE_API_URL` is unset.

Use the provided script, which builds, uploads with correct MIME types, invalidates CloudFront, and verifies the result:

```powershell
.\scripts\deploy-frontend.ps1 -BucketName <bucket> -ApiUrl https://yourdomain.com -DistributionId <EDIST_ID>
```

---

## 12. SSL / HTTPS (Certbot)

```bash
# Obtain a certificate (Nginx plugin handles site config automatically)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run

# Certbot sets up a systemd timer for auto-renewal — verify it is active
sudo systemctl status certbot.timer
```

---

## 13. Storage: Local vs S3

### Local storage (default)

Documents are stored in `/app/storage/standards/` inside the container, backed by a named Docker volume (`ists_document_storage`).

```bash
# Inspect volume location on the host
docker volume inspect ists_document_storage
```

**Limitation:** Files are tied to this EC2 instance. If you replace the instance or scale horizontally, files will be lost or inaccessible.

### S3 storage (recommended for production)

1. Create an S3 bucket (e.g. `ists-documents-prod`) in your AWS region with versioning enabled.
2. Create an IAM user or role with the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::ists-documents-prod",
        "arn:aws:s3:::ists-documents-prod/*"
      ]
    }
  ]
}
```

3. Set in `.env`:

```dotenv
STORAGE_BACKEND=s3
S3_BUCKET_NAME=ists-documents-prod
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxx
```

---

## 14. SMTP / Email Setup

The application sends email notifications via SMTP. In production replace MailHog with a real mail relay.

### AWS SES (recommended)

1. Verify your sending domain in SES console.
2. Request production access (removes sandbox sending restrictions).
3. Create SMTP credentials in SES → Account dashboard → SMTP settings.

```dotenv
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=<SES SMTP username>
SMTP_PASSWORD=<SES SMTP password>
SMTP_USE_TLS=true
SMTP_FROM_ADDRESS=noreply@yourdomain.com
```

### SendGrid

```dotenv
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<your SendGrid API key>
SMTP_USE_TLS=true
SMTP_FROM_ADDRESS=noreply@yourdomain.com
```

---

## 15. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Async PostgreSQL URL (asyncpg) |
| `DATABASE_SYNC_URL` | Yes | — | Sync PostgreSQL URL (psycopg2, used by Celery Beat) |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis broker URL |
| `SECRET_KEY` | Yes | — | JWT signing secret — **must be changed** |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `JWT_EXPIRE_HOURS` | No | `8` | Access token lifetime in hours |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime in days |
| `PASSWORD_RESET_TOKEN_EXPIRE_HOURS` | No | `1` | Password reset token lifetime |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `MAX_UPLOAD_SIZE_MB` | No | `200` | Max document upload size. Keep nginx `client_max_body_size` above this |
| `LOCAL_STORAGE_PATH` | No | `/app/storage` | Path inside container for local storage |
| `S3_BUCKET_NAME` | If S3 | — | S3 bucket name |
| `AWS_REGION` | If S3 | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | If S3 | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | If S3 | — | AWS secret key |
| `SMTP_HOST` | Yes (email) | — | SMTP server hostname |
| `SMTP_PORT` | Yes (email) | `1025` | SMTP port (587 for TLS) |
| `SMTP_USER` | Yes (email) | — | SMTP username |
| `SMTP_PASSWORD` | Yes (email) | — | SMTP password |
| `SMTP_USE_TLS` | No | `false` | Enable STARTTLS |
| `SMTP_FROM_ADDRESS` | No | `ists@local` | Sender email address |
| `CORS_ORIGINS` | Yes | — | Comma-separated allowed origins (your domain) |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `API_KEY_ENCRYPTION_KEY` | Yes | — | Fernet key encrypting stored rss2json.com API keys (see `/api-keys`) |
| `RATE_LIMIT_AUTH` | No | `60/minute` | Rate limit for auth endpoints |
| `RATE_LIMIT_DEFAULT` | No | `300/minute` | Rate limit for general API endpoints |

---

## 16. Service Health Checks

```bash
# All containers running?
docker compose ps

# API health endpoint
curl http://localhost:8000/health

# Database reachable from web container?
docker compose exec web python -c "
import asyncio, asyncpg
async def check():
    conn = await asyncpg.connect('postgresql://ists:PASSWORD@db:5432/ists')
    print('DB OK:', await conn.fetchval('SELECT version()'))
    await conn.close()
asyncio.run(check())
"

# Redis reachable?
docker compose exec redis redis-cli ping
# Expected: PONG

# Celery worker alive?
docker compose exec worker celery -A app.celery_app inspect ping

# Celery Beat schedule loaded?
docker compose exec web python -m alembic current
```

---

## 17. Updating the Application

```bash
cd /opt/ists

# Pull latest code
git pull origin main

# Rebuild backend image (only if Python dependencies or Dockerfile changed)
docker compose build web

# Restart services with zero-downtime approach
docker compose up -d --no-deps --force-recreate web worker beat

# Run any new migrations
docker compose exec web python -m alembic upgrade head

# If frontend changed — rebuild static files
cd frontend
npm install
npm run build
cd ..

# Reload Nginx to serve updated static files
sudo systemctl reload nginx
```

---

## 18. Logs

```bash
# All services (live follow)
docker compose logs -f

# Individual service
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f db

# Last 100 lines from a service
docker compose logs --tail=100 worker

# Filter for errors
docker compose logs worker 2>&1 | grep -i "error\|exception\|traceback"
```

---

## 19. Security Checklist

Before going live, verify each item:

- [ ] `SECRET_KEY` is a random 64-character hex string (not the default)
- [ ] `POSTGRES_PASSWORD` is a strong, unique password
- [ ] `.env` file permissions are restricted: `chmod 600 .env`
- [ ] PostgreSQL port `5432` is **not** exposed to the internet (remove from `ports:` in prod compose)
- [ ] Redis port `6379` is **not** exposed to the internet
- [ ] API port `8000` is **not** exposed to the internet (traffic goes through Nginx only)
- [ ] `ENVIRONMENT=production` is set in `.env`
- [ ] `CORS_ORIGINS` lists only your exact production domain
- [ ] HTTPS is enforced — HTTP redirects to HTTPS
- [ ] Certbot auto-renewal timer is active
- [ ] Admin password changed from default `Admin1234!` immediately after first login
- [ ] MailHog is **not** running in production (it is a dev-only catch-all mail server)
- [ ] EC2 security group only allows ports 22, 80, 443 from appropriate sources
- [ ] SSH key-based authentication only (disable password SSH login)
- [ ] S3 bucket (if used) is private — no public read access
- [ ] `LOG_LEVEL=INFO` in production (avoid `DEBUG` which may log sensitive data)

---

## 20. Ports Reference

| Port | Service | Exposure in Production |
|---|---|---|
| `5432` | PostgreSQL | Internal Docker network only |
| `6379` | Redis | Internal Docker network only |
| `8000` | FastAPI (Uvicorn/Gunicorn) | `127.0.0.1` only — Nginx proxies to it |
| `80` | Nginx HTTP | Public — redirects to 443 |
| `443` | Nginx HTTPS | Public |
| `1025` | MailHog SMTP | **Dev only — remove in production** |
| `8025` | MailHog Web UI | **Dev only — remove in production** |
| `5173` | Vite dev server | **Dev only — not used in production** |

---

*Generated for StandardSphere v1.0.0*
