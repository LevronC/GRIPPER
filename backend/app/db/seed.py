from __future__ import annotations

import logging
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.core.config import settings
from app import models
from app.db.session import _engine_kwargs

logger = logging.getLogger(__name__)

DEFAULT_INSTITUTIONS = [
    {
        "id": uuid.UUID("4229435f-f427-4b6b-a432-1f6488157381"),
        "name": "Stetson University",
        "slug": "stetson",
        "tier": "enterprise",
    },
    {
        "id": uuid.UUID("7c8d9e0f-1a2b-3c4d-5e6f-708192a3b4c5"),
        "name": "University of Florida",
        "slug": "uf",
        "tier": "enterprise",
    },
    {
        "id": uuid.UUID("9e0f1a2b-3c4d-5e6f-7081-92a3b4c5d6e7"),
        "name": "RGIP Demo Program",
        "slug": "rgip-demo",
        "tier": "free",
    },
]

DEMO_USER = {
    "email": "analyst@stetson.edu",
    "password": "Gripp3rDemo!",
    "role": "analyst",
    "graduation_year": 2026,
    "institution_slug": "stetson",
}


def seed_default_data() -> None:
    try:
        engine = create_engine(
            settings.SUPERUSER_DATABASE_URL,
            **_engine_kwargs(settings.SUPERUSER_DATABASE_URL),
        )
        Session = sessionmaker(bind=engine)
    except Exception as exc:
        logger.warning("Skipping seed: database unavailable (%s)", exc)
        return

    with Session() as db:
        try:
            for item in DEFAULT_INSTITUTIONS:
                existing = (
                    db.query(models.Institution)
                    .filter(models.Institution.slug == item["slug"])
                    .first()
                )
                if existing:
                    continue
                db.add(
                    models.Institution(
                        id=item["id"],
                        name=item["name"],
                        slug=item["slug"],
                        tier=item["tier"],
                    )
                )

            stetson = (
                db.query(models.Institution)
                .filter(models.Institution.slug == DEMO_USER["institution_slug"])
                .first()
            )
            if stetson:
                portfolio = (
                    db.query(models.Portfolio)
                    .filter(
                        models.Portfolio.institution_id == stetson.id,
                        models.Portfolio.name == "Stetson George Value Fund",
                    )
                    .first()
                )
                if not portfolio:
                    db.add(
                        models.Portfolio(
                            institution_id=stetson.id,
                            name="Stetson George Value Fund",
                            strategy_type="value",
                        )
                    )

                demo_user = (
                    db.query(models.User)
                    .filter(models.User.email == DEMO_USER["email"])
                    .first()
                )
                if not demo_user:
                    db.add(
                        models.User(
                            email=DEMO_USER["email"],
                            hashed_password=security.get_password_hash(DEMO_USER["password"]),
                            institution_id=stetson.id,
                            role=DEMO_USER["role"],
                            graduation_year=DEMO_USER["graduation_year"],
                            is_verified=True,
                        )
                    )

            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Seed skipped or partially failed (%s)", exc)
