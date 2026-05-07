"""
API v1 router — aggregates all endpoint routers.
New feature modules are registered here.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    crimes,
    alerts,
    fir,
    hotspots,
    ml,
    nlp,
    patrol,
    simulation,
    users,
    websockets,
)

router = APIRouter()

router.include_router(auth.router,        prefix="/auth",       tags=["Authentication"])
router.include_router(users.router,       prefix="/users",      tags=["Users"])
router.include_router(crimes.router,      prefix="/crimes",     tags=["Crimes"])
router.include_router(alerts.router,      prefix="/alerts",     tags=["Alerts"])
router.include_router(fir.router,         prefix="/fir",        tags=["FIR Analysis"])
router.include_router(hotspots.router,    prefix="/hotspots",   tags=["Hotspots"])
router.include_router(ml.router,          prefix="/ml",         tags=["ML Services"])
router.include_router(nlp.router,         prefix="/nlp",        tags=["NLP Services"])
router.include_router(patrol.router,      prefix="/patrol",     tags=["Patrol Optimization"])
router.include_router(simulation.router,  prefix="/simulation", tags=["What-If Simulation"])
router.include_router(websockets.router,  prefix="/ws",         tags=["WebSockets"])
