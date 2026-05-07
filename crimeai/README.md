# CrimeAI — Intelligent Crime Analysis & Predictive Policing Platform

> Production-grade law enforcement analytics built on FastAPI, React, PostgreSQL/PostGIS, Redis, and ML.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| State | Zustand + TanStack Query |
| Maps | Leaflet.js + react-leaflet |
| Backend | FastAPI (Python 3.11) + async SQLAlchemy |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + PostGIS + pgvector |
| ML | scikit-learn + XGBoost + sentence-transformers |
| NLP | spaCy 3 + HuggingFace |
| Auth | JWT (python-jose) + bcrypt |
| Deployment | Vercel + Render + Supabase + Upstash |

## Quick Start (Local Dev)

```bash
# 1. Clone and configure
git clone https://github.com/your-org/crimeai
cd crimeai
cp backend/.env.example backend/.env
# Edit backend/.env with your values

# 2. Start all services
docker compose -f docker-compose.dev.yml up --build

# 3. Run migrations + seed data (first time only)
docker exec crimeai_api alembic upgrade head
docker exec crimeai_api python scripts/seed_data.py

# 4. Start frontend
cd frontend && npm install && npm run dev
```

Access:
- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- API: http://localhost:8000/api/v1

Default credentials:
- Admin: `admin@crimeai.app` / `Admin@1234`
- Officer: `officer01@crimeai.app` / `Officer@01`

## Build Steps

| Step | Content |
|------|---------|
| ✅ Step 1 | Scaffolding, config, Docker, DB schema, CI/CD |
| 🔲 Step 2 | Database schema deep-dive + seed data |
| 🔲 Step 3 | Auth, user management, RBAC |
| 🔲 Step 4 | Crime CRUD, geo queries, caching |
| 🔲 Step 5 | ML: DBSCAN, Random Forest, risk scoring |
| 🔲 Step 6 | NLP: spaCy FIR parser, similarity engine |
| 🔲 Step 7 | Graph service, Celery workers, WebSockets |
| 🔲 Step 8 | React setup, routing, auth UI |
| 🔲 Step 9 | Dashboard page |
| 🔲 Step 10 | Crime Map page |
| 🔲 Step 11 | FIR Analysis page |
| 🔲 Step 12 | Patrol + Simulation pages |
| 🔲 Step 13 | Admin panel, PDF export |
| 🔲 Step 14 | Deployment + final testing |

## Project Structure

```
crimeai/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Endpoints + middleware
│   │   ├── core/            # Config, security, logging, exceptions
│   │   ├── db/              # SQLAlchemy engine, Redis client
│   │   ├── models/          # ORM models
│   │   ├── repositories/    # DB queries
│   │   ├── services/        # Business logic
│   │   ├── schemas/         # Pydantic models
│   │   ├── ml/              # ML modules
│   │   ├── nlp/             # NLP modules
│   │   ├── graph/           # Graph algorithms
│   │   └── workers/         # Celery tasks
│   ├── alembic/             # DB migrations
│   ├── tests/               # pytest test suite
│   └── scripts/             # Seed, utilities
├── frontend/
│   └── src/
│       ├── components/      # Reusable UI
│       ├── pages/           # Route pages
│       ├── store/           # Zustand stores
│       ├── services/        # API clients
│       └── types/           # TypeScript types
├── infrastructure/
│   └── nginx/               # NGINX config
├── scripts/db/              # SQL init scripts
├── .github/workflows/       # CI/CD
└── docker-compose.dev.yml
```

## Security Notes
- JWT tokens expire in 60 minutes (configurable)
- Refresh tokens expire in 7 days
- All passwords hashed with bcrypt
- Rate limiting per user/IP via slowapi
- Full audit log of all authenticated requests
- CORS restricted to configured origins
- SQL injection prevention via SQLAlchemy ORM
- XSS prevention via Pydantic input validation

## License
Proprietary — Law Enforcement Use Only
