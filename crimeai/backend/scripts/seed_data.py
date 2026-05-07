#!/usr/bin/env python3
"""
Seed script: populates the database with realistic mock crime data.
Run with: python scripts/seed_data.py
Creates: 1 admin, 5 officers, 500 crimes across districts.
"""
from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.alert import Alert
from app.models.crime import Crime
from app.models.fir import FIRReport
from app.models.user import User

fake = Faker("en_IN")  # Indian locale for realistic FIR data

CRIME_TYPES = [
    ("theft", ["bike theft", "mobile snatching", "pickpocket", "burglary"]),
    ("assault", ["physical assault", "road rage", "domestic violence"]),
    ("robbery", ["armed robbery", "chain snatching"]),
    ("fraud", ["online fraud", "cheque fraud", "impersonation"]),
    ("drug_offense", ["possession", "trafficking", "under_influence"]),
    ("vandalism", ["property damage", "graffiti"]),
    ("trespass", ["residential", "commercial"]),
]

# Districts with realistic lat/lng (Delhi NCR area)
DISTRICTS = [
    {"name": "Connaught Place",  "lat": 28.6315, "lng": 77.2167},
    {"name": "Karol Bagh",       "lat": 28.6525, "lng": 77.1900},
    {"name": "Rohini",           "lat": 28.7409, "lng": 77.0678},
    {"name": "Dwarka",           "lat": 28.5921, "lng": 77.0460},
    {"name": "Saket",            "lat": 28.5245, "lng": 77.2066},
    {"name": "Lajpat Nagar",     "lat": 28.5674, "lng": 77.2430},
    {"name": "Janakpuri",        "lat": 28.6270, "lng": 77.0837},
    {"name": "Shahdara",         "lat": 28.6757, "lng": 77.2900},
]

SEVERITIES = [1, 1, 1, 2, 2, 3, 3, 4, 5]  # Weighted toward lower severity


async def seed(db: AsyncSession) -> None:
    # Guard: skip if data already exists
    from sqlalchemy import text as sql_text
    count_result = await db.execute(sql_text("SELECT COUNT(*) FROM users"))
    existing = count_result.scalar_one()
    if existing > 0:
        print(f"⚠️  Database already has {existing} users. Skipping seed.")
        print("   Use --force flag to re-seed: python scripts/seed_data.py --force")
        return

    print("🌱 Seeding database...")

    # ── Users ─────────────────────────────────────────────────────────────────
    admin = User(
        email="admin@crimeai.app",
        hashed_password=hash_password("Admin@1234"),
        full_name="System Administrator",
        role="admin",
        is_active=True,
    )
    db.add(admin)

    officers = []
    for i in range(1, 6):
        officer = User(
            email=f"officer{i:02d}@crimeai.app",
            hashed_password=hash_password(f"Officer@{i:02d}"),
            full_name=fake.name(),
            role="police",
            badge_number=f"DL-{1000 + i}",
            department=random.choice(["Central", "North", "South", "East", "West"]),
            is_active=True,
        )
        db.add(officer)
        officers.append(officer)

    await db.flush()
    print(f"  ✅ Created 1 admin + {len(officers)} officers")

    # ── Crimes ────────────────────────────────────────────────────────────────
    crimes = []
    now = datetime.now(timezone.utc)
    for i in range(500):
        district = random.choice(DISTRICTS)
        crime_type, sub_types = random.choice(CRIME_TYPES)
        # Add jitter to coordinates (±0.02 degrees ≈ 2km)
        lat = district["lat"] + random.uniform(-0.02, 0.02)
        lng = district["lng"] + random.uniform(-0.02, 0.02)
        occurred = now - timedelta(days=random.randint(0, 365))

        crime = Crime(
            crime_type=crime_type,
            sub_type=random.choice(sub_types),
            description=fake.sentence(nb_words=15),
            severity=random.choice(SEVERITIES),
            location_name=fake.street_name(),
            address=fake.address(),
            district=district["name"],
            city="Delhi",
            latitude=lat,
            longitude=lng,
            geom=f"SRID=4326;POINT({lng} {lat})",
            occurred_at=occurred,
            status=random.choice(["reported", "under_investigation", "resolved"]),
            case_number=f"DL-{now.year}-{10000 + i}",
            assigned_officer_id=random.choice(officers).id,
        )
        db.add(crime)
        crimes.append(crime)

    await db.flush()
    print(f"  ✅ Created {len(crimes)} crimes")

    # ── FIR Reports (for 50 crimes) ───────────────────────────────────────────
    for crime in random.sample(crimes, 50):
        fir = FIRReport(
            fir_number=f"FIR-{crime.case_number}",
            crime_id=crime.id,
            submitted_by=random.choice(officers).id,
            raw_text=(
                f"On {crime.occurred_at.strftime('%d/%m/%Y')} at approximately "
                f"{crime.occurred_at.strftime('%H:%M')}, a {crime.crime_type} incident "
                f"({crime.sub_type}) was reported at {crime.address}, {crime.district}. "
                f"{crime.description} The complainant reported this to the duty officer "
                f"and the case was registered under relevant IPC sections."
            ),
            nlp_status="pending",
        )
        db.add(fir)

    # ── Sample Alerts ─────────────────────────────────────────────────────────
    for district in random.sample(DISTRICTS, 3):
        alert = Alert(
            title=f"High crime activity in {district['name']}",
            message=f"Unusual spike in theft cases detected in {district['name']} district. Patrol recommended.",
            alert_type="hotspot",
            severity="high",
            latitude=district["lat"],
            longitude=district["lng"],
            district=district["name"],
        )
        db.add(alert)

    await db.commit()
    print("  ✅ Created 50 FIR reports + 3 alerts")
    print("\n✅ Seeding complete!")
    print("\n📋 Login credentials:")
    print("   Admin:   admin@crimeai.app / Admin@1234")
    print("   Officer: officer01@crimeai.app / Officer@01")


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await seed(db)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
