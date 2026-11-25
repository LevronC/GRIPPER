"""
Create SYNTHETIC demonstration data for local development.

    ENVIRONMENT=development MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/gripper \
        DEMO_PASSWORD='choose-a-local-password' python scripts/seed_demo.py

* Refuses to run when ENVIRONMENT=production, on Vercel, or against a non-local
  database host (override the host check with --allow-remote-db; production is never allowed).
* Everything lives in one synthetic institution (slug `synthetic-demo`); no real
  institution, person or fund is referenced. Re-running is idempotent.
* Creates one portfolio, holdings and three IPS rules chosen so that evaluating the
  portfolio produces known, deterministic violations (see EXPECTED_VIOLATIONS).
* Demo passwords come from DEMO_PASSWORD; if unset, a random one is generated and
  printed once to this terminal. Nothing is created with a publicly known password.
"""

from __future__ import annotations

import argparse
import os
import secrets
import uuid

from _cli import owner_engine, refuse_unless_local_development
from sqlalchemy import text

from app.core.security import get_password_hash, validate_password_policy

DEMO_SLUG = "synthetic-demo"
DEMO_NAME = "Synthetic Demo Fund (not a real institution)"
DEMO_USERS = (
    ("demo-admin@synthetic-demo.example", "admin"),
    ("demo-pm@synthetic-demo.example", "pm"),
    ("demo-analyst@synthetic-demo.example", "analyst"),
)

DEMO_PORTFOLIO = "Synthetic Growth Portfolio"
# (ticker, weight, cost_basis). Weights are fractions of portfolio value; total 0.93.
DEMO_HOLDINGS = (
    ("NVDA", 0.14, 480.0),
    ("MSFT", 0.09, 410.0),
    ("AAPL", 0.08, 190.0),
    ("JPM", 0.10, 200.0),
    ("XOM", 0.09, 110.0),
    ("JNJ", 0.10, 155.0),
    ("LLY", 0.10, 760.0),
    ("AMZN", 0.10, 180.0),
    ("MCRT", 0.04, 12.0),   # synthetic micro-cap in TICKER_METADATA
    ("GCAP", 0.04, 8.0),    # synthetic micro-cap in TICKER_METADATA
    ("BAC", 0.05, 38.0),
)
DEMO_RULES = (
    ("single_position_cap", 0.10, "critical"),
    ("sector_exposure_cap", 0.30, "warning"),
    ("liquidity_constraint", 0.05, "warning"),
)
# What `POST /portfolios/{id}/evaluate` must return for this data:
EXPECTED_VIOLATIONS = {
    ("single_position_cap", "NVDA"),           # 14% > 10%
    ("sector_exposure_cap", "Technology"),     # NVDA+MSFT+AAPL+MCRT = 35% > 30%
    ("liquidity_constraint", None),            # MCRT+GCAP = 8% > 5%
}


def seed(conn, password_hash: str) -> uuid.UUID:
    inst_id = conn.execute(text("SELECT id FROM institutions WHERE slug = :s"), {"s": DEMO_SLUG}).scalar()
    if inst_id is None:
        inst_id = uuid.uuid4()
        conn.execute(
            text("INSERT INTO institutions (id, name, slug, tier, created_at) VALUES (:i, :n, :s, 'free', now())"),
            {"i": inst_id, "n": DEMO_NAME, "s": DEMO_SLUG},
        )
    for email, role in DEMO_USERS:
        conn.execute(
            text(
                "INSERT INTO users (id, institution_id, email, hashed_password, role, is_verified, token_version, created_at) "
                "VALUES (:u, :i, :e, :h, :r, true, 0, now()) "
                "ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password, "
                "token_version = users.token_version + 1"
            ),
            {"u": uuid.uuid4(), "i": inst_id, "e": email, "h": password_hash, "r": role},
        )

    portfolio_id = conn.execute(
        text("SELECT id FROM portfolios WHERE institution_id = :i AND name = :n"),
        {"i": inst_id, "n": DEMO_PORTFOLIO},
    ).scalar()
    if portfolio_id is None:
        portfolio_id = uuid.uuid4()
        conn.execute(
            text("INSERT INTO portfolios (id, institution_id, name, strategy_type, created_at) "
                 "VALUES (:p, :i, :n, 'growth', now())"),
            {"p": portfolio_id, "i": inst_id, "n": DEMO_PORTFOLIO},
        )
    conn.execute(text("DELETE FROM holdings WHERE portfolio_id = :p"), {"p": portfolio_id})
    for ticker, weight, cost in DEMO_HOLDINGS:
        conn.execute(
            text("INSERT INTO holdings (id, portfolio_id, ticker, weight, cost_basis, updated_at) "
                 "VALUES (:h, :p, :t, :w, :c, now())"),
            {"h": uuid.uuid4(), "p": portfolio_id, "t": ticker, "w": weight, "c": cost},
        )
    for rule_type, threshold, severity in DEMO_RULES:
        exists = conn.execute(
            text("SELECT 1 FROM ips_rules WHERE institution_id = :i AND rule_type = :t AND active"),
            {"i": inst_id, "t": rule_type},
        ).first()
        if not exists:
            conn.execute(
                text("INSERT INTO ips_rules (id, institution_id, rule_type, threshold, severity, active, created_at) "
                     "VALUES (:r, :i, :t, :th, :s, true, now())"),
                {"r": uuid.uuid4(), "i": inst_id, "t": rule_type, "th": threshold, "s": severity},
            )
    return inst_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-remote-db", action="store_true")
    args = ap.parse_args()
    refuse_unless_local_development(allow_remote=args.allow_remote_db)

    password = os.environ.get("DEMO_PASSWORD")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(12)
    validate_password_policy(password)

    with owner_engine().begin() as conn:
        inst_id = seed(conn, get_password_hash(password))

    print(f"Seeded synthetic institution {DEMO_SLUG} ({inst_id}). Accounts:")
    for email, role in DEMO_USERS:
        print(f"  {role:8s} {email}")
    print(f"Portfolio '{DEMO_PORTFOLIO}' with {len(DEMO_HOLDINGS)} holdings and {len(DEMO_RULES)} IPS rules.")
    print("Sign in as demo-pm and run Evaluate to see the seeded violations.")
    if generated:
        print(f"Generated password (shown once, all demo accounts): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
