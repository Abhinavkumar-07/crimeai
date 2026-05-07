# CrimeAI — Complete Deployment Guide (Free Tier)

## Prerequisites
- GitHub account
- Supabase account → https://supabase.com
- Upstash account → https://upstash.com
- Render account → https://render.com
- Vercel account → https://vercel.com

---

## Step 1 — Supabase (PostgreSQL + Storage)

1. **New Project**: supabase.com → New project → note your password
2. **Enable extensions** (SQL Editor → New query):
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS postgis_topology;
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   ```
3. **Get connection strings** (Settings → Database):
   - *Session pooler* → `postgresql://postgres:[password]@aws-0-[region].pooler.supabase.com:5432/postgres`  
     → This is your `DATABASE_URL_SYNC`
   - Prepend `postgresql+asyncpg://` for `DATABASE_URL`
4. **Storage bucket**: Storage → New bucket → Name: `fir-documents` → Private

---

## Step 2 — Upstash Redis

1. upstash.com → Create Database → pick region closest to your Render region
2. Copy **Redis URL** (format: `rediss://default:xxx@xxx.upstash.io:6379`)
3. Set this as `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
   - For Celery, append `/1` and `/2` respectively:
     - `CELERY_BROKER_URL=rediss://...@upstash.io:6379/1`
     - `CELERY_RESULT_BACKEND=rediss://...@upstash.io:6379/2`

---

## Step 3 — Render (Backend API + Workers)

### API Service
1. render.com → New Web Service → Connect GitHub repo
2. Settings:
   - **Root directory**: `backend`
   - **Build command**: `pip install -r requirements.txt && python -m spacy download en_core_web_sm`
   - **Start command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
3. **Environment variables** (set all from `.env.example`):
   ```
   APP_ENV=production
   APP_SECRET_KEY=<generate with: openssl rand -hex 32>
   JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
   DATABASE_URL=postgresql+asyncpg://postgres:[pass]@[host]:5432/postgres
   DATABASE_URL_SYNC=postgresql://postgres:[pass]@[host]:5432/postgres
   REDIS_URL=rediss://...@upstash.io:6379
   CELERY_BROKER_URL=rediss://...@upstash.io:6379/1
   CELERY_RESULT_BACKEND=rediss://...@upstash.io:6379/2
   ALLOWED_ORIGINS=https://your-app.vercel.app
   DOCS_ENABLED=false
   SPACY_MODEL=en_core_web_sm
   ```
4. Health check path: `/health`

### Celery Worker
1. New Background Worker → same repo
2. Root directory: `backend`
3. Build: same as API
4. Start: `celery -A app.workers.celery_app:celery_app worker --loglevel=info --concurrency=2 --queues=default,ml,nlp`
5. Same environment variables as API

### Celery Beat
1. New Background Worker
2. Start: `celery -A app.workers.celery_app:celery_app beat --loglevel=info`
3. Same environment variables

---

## Step 4 — Database Setup

After first Render deploy, open Shell on the API service:

```bash
# Run all migrations
alembic upgrade head

# Seed demo data (500 crimes, users, FIRs, alerts)
python scripts/seed_data.py
```

Login credentials after seeding:
- Admin: `admin@crimeai.app` / `Admin@1234`
- Officer: `officer01@crimeai.app` / `Officer@01`

---

## Step 5 — Vercel (Frontend)

1. vercel.com → New Project → Import your GitHub repo
2. **Framework preset**: Vite
3. **Root directory**: `frontend`
4. **Environment variables**:
   ```
   VITE_API_URL=https://crimeai-api.onrender.com
   VITE_WS_URL=wss://crimeai-api.onrender.com
   VITE_APP_NAME=CrimeAI
   ```
5. Deploy → copy your Vercel URL (e.g. `https://crimeai.vercel.app`)
6. **Update Render** `ALLOWED_ORIGINS` to include your Vercel URL

---

## Step 6 — GitHub Actions Secrets

Settings → Secrets and variables → Actions → New secret:

| Secret | Value |
|--------|-------|
| `RENDER_DEPLOY_HOOK_URL` | Render → API Service → Settings → Deploy Hook |
| `VERCEL_TOKEN` | vercel.com → Settings → Tokens |

---

## Step 7 — ML Initialization (post-deploy)

After deploy, via Render Shell or API calls:

```bash
# 1. Train hotspot prediction model
curl -X POST https://crimeai-api.onrender.com/api/v1/ml/hotspot-prediction \
  -H "Authorization: Bearer <admin_jwt>"

# 2. Run initial DBSCAN clustering
curl -X POST https://crimeai-api.onrender.com/api/v1/ml/cluster?auto_eps=true \
  -H "Authorization: Bearer <admin_jwt>"

# 3. Generate crime embeddings for similarity search
curl -X POST "https://crimeai-api.onrender.com/api/v1/ml/embed-crimes?limit=500" \
  -H "Authorization: Bearer <admin_jwt>"
```

---

## Free Tier Limits & Mitigation

| Service | Free Limit | Mitigation |
|---------|-----------|-----------|
| Render API | Spins down after 15min idle | Add UptimeRobot to ping `/health` every 5min |
| Render Worker | 750h/month | Workers stay active; use sparingly |
| Supabase DB | 500MB storage | Sufficient for ~50k crimes |
| Upstash Redis | 10k commands/day | Generous TTLs on cached data |
| Vercel | Unlimited hobby | Production-ready for this scale |

---

## Scaling Beyond Free Tier

When traffic grows:
- **DB**: Supabase Pro ($25/mo) — 8GB, no pauses, daily backups
- **API**: Render Starter ($7/mo/instance) — always-on, more RAM
- **Workers**: Add more Render workers for ML/NLP queues
- **Horizontal**: Add NGINX load balancer, run 3+ API instances
