import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add root backend folder to path
sys.path.insert(0, os.path.realpath(os.path.dirname(__file__)))

from app import models

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://gripper_app:gripper_secure@localhost:5432/gripper")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def verify_rls():
    try:
        # Step 1: Clean up and create institutions using superuser
        print("Cleaning up old database records and creating tenants...")
        super_engine = create_engine("postgresql://civicpulse:civicpulse@localhost:5432/gripper")
        SuperSession = sessionmaker(bind=super_engine)
        
        with SuperSession() as s_db:
            s_db.query(models.Portfolio).delete()
            s_db.query(models.Institution).delete()
            
            stetson = models.Institution(name="Stetson University", slug="stetson")
            uf = models.Institution(name="University of Florida", slug="uf")
            s_db.add_all([stetson, uf])
            s_db.commit()
            
            stetson_id = stetson.id
            uf_id = uf.id
            print(f"Stetson ID: {stetson_id}")
            print(f"UF ID: {uf_id}")

        print("\nCreating portfolios under tenant contexts...")
        # Step 2: Insert Stetson Portfolio using SET LOCAL in explicit transaction
        with SessionLocal() as db:
            with db.begin():
                db.execute(text("SET LOCAL app.current_institution_id = :id"), {"id": str(stetson_id)})
                p1 = models.Portfolio(institution_id=stetson_id, name="Stetson George Value Fund", strategy_type="value")
                db.add(p1)

        # Step 3: Insert UF Portfolio using SET LOCAL in explicit transaction
        with SessionLocal() as db:
            with db.begin():
                db.execute(text("SET LOCAL app.current_institution_id = :id"), {"id": str(uf_id)})
                p2 = models.Portfolio(institution_id=uf_id, name="Gator Growth Fund", strategy_type="growth")
                db.add(p2)

        print("Portfolios created successfully.")

        # --- TEST 1: Retrieve as Stetson ---
        print("\n--- TEST 1: Retrieve as Stetson ---")
        with SessionLocal() as db:
            with db.begin():
                db.execute(text("SET LOCAL app.current_institution_id = :id"), {"id": str(stetson_id)})
                stetson_portfolios = db.query(models.Portfolio).all()
                print(f"Retrieved portfolios count: {len(stetson_portfolios)}")
                for p in stetson_portfolios:
                    print(f"- Portfolio: {p.name} (Tenant: {p.institution_id})")
                
                assert len(stetson_portfolios) == 1
                assert stetson_portfolios[0].institution_id == stetson_id
                print("TEST 1 SUCCESS: Only Stetson portfolios retrieved!")

        # --- TEST 2: Retrieve as UF ---
        print("\n--- TEST 2: Retrieve as UF ---")
        with SessionLocal() as db:
            with db.begin():
                db.execute(text("SET LOCAL app.current_institution_id = :id"), {"id": str(uf_id)})
                uf_portfolios = db.query(models.Portfolio).all()
                print(f"Retrieved portfolios count: {len(uf_portfolios)}")
                for p in uf_portfolios:
                    print(f"- Portfolio: {p.name} (Tenant: {p.institution_id})")
                
                assert len(uf_portfolios) == 1
                assert uf_portfolios[0].institution_id == uf_id
                print("TEST 2 SUCCESS: Only UF portfolios retrieved!")

        # --- TEST 3: Retrieve without setting context ---
        print("\n--- TEST 3: Retrieve without tenant context ---")
        with SessionLocal() as db:
            with db.begin():
                # Since app.current_institution_id is not set, RLS should filter out all portfolios
                all_portfolios = db.query(models.Portfolio).all()
                print(f"Retrieved portfolios count: {len(all_portfolios)}")
                
                assert len(all_portfolios) == 0
                print("TEST 3 SUCCESS: No portfolios retrieved without tenant ID!")

        print("\n🎉 ALL RLS ISOLATION TESTS PASSED SUCCESSFULLY! 🎉")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: RLS boundary violated! ❌")
        raise e
    except Exception as e:
        print(f"\n❌ ERROR RUNNING TESTS: {e} ❌")
        raise e

if __name__ == "__main__":
    verify_rls()
