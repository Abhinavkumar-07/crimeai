# CrimeAI — API Endpoints Reference

Base URL: `/api/v1`

## Authentication
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | None | Login, returns JWT tokens |
| POST | `/auth/refresh` | None | Exchange refresh token |
| POST | `/auth/register` | None | Create account |

## Users
| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/users/` | Admin | List all users |
| GET | `/users/me` | Any | Current user profile |
| DELETE | `/users/{id}` | Admin | Deactivate user |

## Crimes
| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/crimes/` | Police | List crimes (filterable) |
| POST | `/crimes/` | Police | Create crime record |
| GET | `/crimes/{id}` | Police | Get crime by ID |
| PUT | `/crimes/{id}` | Police | Update crime |
| DELETE | `/crimes/{id}` | Admin | Delete crime |
| GET | `/crimes/nearby` | Police | Crimes within radius (PostGIS) |
| GET | `/crimes/export/geojson` | Analyst | Export as GeoJSON |

## Hotspots & ML
| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/hotspots/` | Police | Crime hotspots (cached) |
| GET | `/hotspots/heatmap` | Police | Heatmap data points |
| POST | `/ml/cluster` | Analyst | Trigger DBSCAN clustering |
| GET | `/ml/clusters` | Police | Get current clusters |
| POST | `/ml/predict-risk` | Analyst | Risk score for area |
| GET | `/ml/risk-map` | Police | Risk scores per district |

## FIR Analysis
| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/fir/` | Police | Submit FIR (text or file) |
| GET | `/fir/` | Police | List FIR reports |
| GET | `/fir/{id}` | Police | Get FIR + extracted entities |
| POST | `/fir/{id}/reprocess` | Analyst | Re-run NLP on FIR |

## NLP
| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/nlp/extract` | Police | Extract entities from text |
| POST | `/nlp/similarity` | Analyst | Find similar crimes |
| POST | `/nlp/classify` | Analyst | Classify crime type from text |

## Alerts
| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/alerts/` | Police | List alerts |
| POST | `/alerts/` | Admin | Create manual alert |
| PATCH | `/alerts/{id}/read` | Police | Mark as read |
| PATCH | `/alerts/{id}/resolve` | Police | Resolve alert |

## Patrol Optimization
| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/patrol/optimize` | Police | Generate optimized patrol route |
| GET | `/patrol/routes` | Police | Saved patrol routes |

## What-If Simulation
| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/simulation/run` | Analyst | Run crime scenario simulation |
| GET | `/simulation/{id}` | Analyst | Get simulation results |

## WebSockets
| Path | Description |
|------|-------------|
| `/ws/alerts` | Real-time alert stream (JWT in query param) |

## Health
| Path | Description |
|------|-------------|
| `/health` | Liveness probe |
| `/ready` | Readiness probe (checks DB + Redis) |
