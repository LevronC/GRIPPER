import os
import sys
import uuid
import json
import fitz  # PyMuPDF
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis
from rq import Queue, SimpleWorker

# Configure environment to use non-superuser role so RLS policies are enforced
os.environ["DATABASE_URL"] = "postgresql://gripper_app:gripper_secure@localhost:5432/gripper"

# Add root backend folder to path
sys.path.insert(0, os.path.realpath(os.path.dirname(__file__)))

from app.main import app as fastapi_app
from app.core.config import settings
from app import models
import app.api.endpoints

# Use a unique queue to isolate testing from background/daemon workers
redis_conn = Redis.from_url(settings.REDIS_URL)
test_queue = Queue(f"test_queue_{uuid.uuid4()}", connection=redis_conn)
app.api.endpoints.queue = test_queue

client = TestClient(fastapi_app)

def create_test_pdf(filename: str, content: str):
    """Generates a mock PDF using PyMuPDF"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), content, fontsize=12)
    doc.save(filename)
    doc.close()

def run_burst_worker():
    """Retrieves and executes all enqueued jobs synchronously for deterministic testing"""
    jobs = test_queue.get_jobs()
    print(f"\n[Worker] Found {len(jobs)} background tasks enqueued in test queue.")
    for job in jobs:
        print(f"[Worker] Running job {job.id} synchronously...")
        job.perform()
        test_queue.remove(job.id)



def test_governance_system():
    # Paths for mock files
    tsla_thesis_file = "tsla_exception.pdf"
    tsla_thesis_text = (
        "Stetson George Value Fund sector lead exception buy for TSLA. We maintain a "
        "high allocation of 15% in Tesla (TSLA) due to FSD valuation model updates and "
        "autonomous driving conviction in 2024, bypassing standard 10% IPS caps."
    )
    
    try:
        create_test_pdf(tsla_thesis_file, tsla_thesis_text)
        
        # 1. Database Cleanup using Superuser connection (bypassing RLS)
        print("\n[DB] Initializing test tables via superuser...")
        super_engine = create_engine("postgresql://civicpulse:civicpulse@localhost:5432/gripper")
        SuperSession = sessionmaker(bind=super_engine)
        
        with SuperSession() as s_db:
            # Delete old data
            s_db.query(models.GovernanceEvent).delete()
            s_db.query(models.Holding).delete()
            s_db.query(models.Portfolio).delete()
            s_db.query(models.IPSRule).delete()
            s_db.query(models.DocumentChunk).delete()
            s_db.query(models.ResearchReport).delete()
            s_db.query(models.User).delete()
            s_db.query(models.Institution).delete()
            
            # Create Stetson & UF institutions
            stetson = models.Institution(name="Stetson University", slug="stetson")
            uf = models.Institution(name="University of Florida", slug="uf")
            s_db.add_all([stetson, uf])
            s_db.commit()
            
            stetson_id = str(stetson.id)
            uf_id = str(uf.id)
            
            # Create Stetson rules
            rule1 = models.IPSRule(
                institution_id=stetson.id,
                rule_type="single_position_cap",
                threshold=0.10,  # 10%
                severity="critical"
            )
            rule2 = models.IPSRule(
                institution_id=stetson.id,
                rule_type="sector_exposure_cap",
                threshold=0.30,  # 30% Tech limit
                severity="warning"
            )
            rule3 = models.IPSRule(
                institution_id=stetson.id,
                rule_type="liquidity_constraint",
                threshold=0.05,  # 5% micro-cap limit
                severity="warning"
            )
            s_db.add_all([rule1, rule2, rule3])
            
            # Create Stetson Portfolio
            portfolio = models.Portfolio(
                institution_id=stetson.id,
                name="Stetson George Value Fund",
                strategy_type="value"
            )
            s_db.add(portfolio)
            s_db.commit()
            
            portfolio_id = str(portfolio.id)
            print(f"Stetson Institution ID: {stetson_id}")
            print(f"Stetson Portfolio ID: {portfolio_id}")
            print(f"UF Institution ID: {uf_id}")

        # Register a Stetson PM user
        print("\n[Auth] Registering test user...")
        reg_response = client.post(
            "/auth/register",
            headers={"X-Institution-ID": stetson_id},
            json={
                "email": "analyst@stetson.edu",
                "password": "stetson_secure_pwd",
                "institution_id": stetson_id,
                "role": "pm"
            }
        )
        assert reg_response.status_code == 201
        
        # Login to receive JWT token
        print("\n[Auth] Logging in...")
        login_response = client.post(
            "/auth/login",
            headers={"X-Institution-ID": stetson_id},
            json={
                "email": "analyst@stetson.edu",
                "password": "stetson_secure_pwd"
            }
        )
        assert login_response.status_code == 200
        token_data = login_response.json()
        token = token_data["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Institution-ID": stetson_id
        }

        # 2. Add Compliant Holdings
        # TSLA: 8%, XOM: 10%, BAC: 9% (All under 10% single cap. Combined Tech = 0. Combined micro = 0)
        print("\n[Holdings] Populating compliant holdings...")
        with SuperSession() as s_db:
            h1 = models.Holding(portfolio_id=uuid.UUID(portfolio_id), ticker="TSLA", weight=0.08, cost_basis=180.0)
            h2 = models.Holding(portfolio_id=uuid.UUID(portfolio_id), ticker="XOM", weight=0.10, cost_basis=115.0)
            h3 = models.Holding(portfolio_id=uuid.UUID(portfolio_id), ticker="BAC", weight=0.09, cost_basis=35.0)
            s_db.add_all([h1, h2, h3])
            s_db.commit()
            h1_id = str(h1.id)

        # 3. RUN EVALUATOR - Compliant Portfolio
        print("\n--- TEST 1: Run Compliance Evaluator on Compliant Portfolio ---")
        response = client.post(
            f"/portfolios/{portfolio_id}/evaluate",
            headers=auth_headers
        )
        assert response.status_code == 200
        violations = response.json()["violations"]
        print(f"Violations detected: {len(violations)}")
        assert len(violations) == 0
        print("TEST 1 SUCCESS: Compliant portfolio passed with 0 violations.")

        # 4. Trigger Position Cap Violation
        # Increase TSLA weight to 15% (exceeds 10% single cap limit)
        print("\n[Holdings] Modifying holdings to trigger Single Position Cap Violation...")
        with SuperSession() as s_db:
            tsla_holding = s_db.query(models.Holding).filter(models.Holding.ticker == "TSLA").one()
            tsla_holding.weight = 0.15
            s_db.commit()

        # 5. RUN EVALUATOR - Single Position Cap Violation
        print("\n--- TEST 2: Run Compliance Evaluator (Expecting TSLA violation) ---")
        response = client.post(
            f"/portfolios/{portfolio_id}/evaluate",
            headers=auth_headers
        )
        assert response.status_code == 200
        violations = response.json()["violations"]
        print(f"Violations detected: {len(violations)}")
        for v in violations:
            print(f"- Type: {v['event_type']} | Msg: {v['details']['message']}")
        
        assert len(violations) == 1
        assert violations[0]["event_type"] == "single_position_cap"
        assert violations[0]["details"]["ticker"] == "TSLA"
        tsla_event_id = violations[0]["id"]
        print("TEST 2 SUCCESS: Correctly flagged TSLA weight compliance breach.")

        # 6. Trigger Sector Exposure Cap Violation
        # Add AAPL (20%) and NVDA (15%). Total Tech exposure = 35% (exceeds 30% Tech sector cap)
        print("\n[Holdings] Modifying holdings to trigger Sector Exposure Cap Violation...")
        with SuperSession() as s_db:
            h4 = models.Holding(portfolio_id=uuid.UUID(portfolio_id), ticker="AAPL", weight=0.20, cost_basis=175.0)
            h5 = models.Holding(portfolio_id=uuid.UUID(portfolio_id), ticker="NVDA", weight=0.15, cost_basis=850.0)
            s_db.add_all([h4, h5])
            s_db.commit()

        # 7. RUN EVALUATOR - Multiple Violations (TSLA position cap + Tech sector cap)
        print("\n--- TEST 3: Run Compliance Evaluator (Expecting TSLA + Tech sector violations) ---")
        response = client.post(
            f"/portfolios/{portfolio_id}/evaluate",
            headers=auth_headers
        )
        assert response.status_code == 200
        violations = response.json()["violations"]
        print(f"Violations detected: {len(violations)}")
        for v in violations:
            print(f"- Type: {v['event_type']} | Msg: {v['details']['message']}")
            
        assert len(violations) >= 2
        event_types = [v["event_type"] for v in violations]
        assert "single_position_cap" in event_types
        assert "sector_exposure_cap" in event_types
        print("TEST 3 SUCCESS: Correctly flagged combined position and sector compliance breaches.")

        # 8. Upload TSLA exception memo & run ingestion
        print("\n[RAG Ingestion] Uploading TSLA exception rationale document...")
        with open(tsla_thesis_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                headers=auth_headers,
                data={
                    "sector": "Technology",
                    "company": "Tesla (TSLA)",
                    "recommendation": "buy"
                },
                files={"file": (tsla_thesis_file, f, "application/pdf")}
            )
        assert response.status_code == 202
        
        # Process ingestion in worker synchronously
        run_burst_worker()

        # 9. RUN EXPLAINABILITY ENDPOINT on TSLA event
        print("\n--- TEST 4: Explain TSLA Violation (RAG Search Exception) ---")
        response = client.post(
            f"/violations/{tsla_event_id}/explain",
            headers=auth_headers
        )
        assert response.status_code == 200
        explanation = response.json()
        print("RAG Explanation Result:")
        print(f"- Message: {explanation['message']}")
        print(f"- Compliance Status: {explanation['compliance_status']}")
        print(f"- AI Explanation Draft: {explanation['ai_explanation_draft']}")
        print("- Evidence Retrieved:")
        for ev in explanation["evidence"]:
            print(f"  * Company: {ev['company']} | Text: '{ev['content'][:80]}...' (Page {ev['page']}, Sim: {ev['similarity']:.4f})")
            
        assert explanation["compliance_status"] == "retrieval_justified"
        assert len(explanation["evidence"]) > 0
        assert "TSLA" in explanation["evidence"][0]["content"]
        print("TEST 4 SUCCESS: RAG successfully retrieved the compliance exception rationale.")

        # 10. RESOLVE VIOLATION
        # Reduce TSLA weight back to 8% (under 10% limit)
        print("\n[Holdings] Resolving TSLA breach by reducing weight to 8%...")
        with SuperSession() as s_db:
            tsla_holding = s_db.query(models.Holding).filter(models.Holding.ticker == "TSLA").one()
            tsla_holding.weight = 0.08
            s_db.commit()
            
        # Run compliance audit to update DB state
        print("\n--- TEST 5: Compliance Evaluator (TSLA should be resolved) ---")
        response = client.post(
            f"/portfolios/{portfolio_id}/evaluate",
            headers=auth_headers
        )
        assert response.status_code == 200
        violations = response.json()["violations"]
        print(f"Active violations: {len(violations)}")
        active_single_caps = [v["details"].get("ticker") for v in violations if v["event_type"] == "single_position_cap"]
        assert "TSLA" not in active_single_caps
        
        # Query resolved violations from DB
        response = client.get(
            f"/portfolios/{portfolio_id}/violations?resolved=true",
            headers=auth_headers
        )
        assert response.status_code == 200
        resolved_events = response.json()
        print(f"Resolved events in database: {len(resolved_events)}")
        for re in resolved_events:
            print(f"- Type: {re['event_type']} | Resolved: {re['resolved']} | Resolved At: {re['resolved_at']}")
            
        assert len(resolved_events) == 1
        assert resolved_events[0]["event_type"] == "single_position_cap"
        assert resolved_events[0]["resolved"] is True
        print("TEST 5 SUCCESS: Violation was resolved successfully, closed in DB, and archived in audit trail.")

        # 11. Row-Level Security isolation test
        # Try to query Stetson portfolio's active violations from UF's tenant context
        print("\n--- TEST 6: RLS Tenant Security Isolation ---")
        # UF header fallback (without token)
        response = client.get(
            f"/portfolios/{portfolio_id}/violations?resolved=false",
            headers={"X-Institution-ID": uf_id}
        )
        # Should return empty list because RLS policy filters out rows not belonging to UF
        assert response.status_code == 200
        uf_visible_violations = response.json()
        print(f"Violations visible to UF tenant: {len(uf_visible_violations)}")
        assert len(uf_visible_violations) == 0
        print("TEST 6 SUCCESS: Cross-tenant query returned 0 rows! Security isolation fully enforced.")

        # 12. Scenario Simulation Test
        print("\n--- TEST 7: Compliance Simulation Sandbox ---")
        sim_response = client.post(
            f"/portfolios/{portfolio_id}/simulate",
            headers=auth_headers,
            json=[
                {"ticker": "AMZN", "weight": 0.15}, # Exceeds 10% single cap rule
                {"ticker": "BAC", "weight": 0.05}
            ]
        )
        assert sim_response.status_code == 200
        sim_data = sim_response.json()
        sim_violations = sim_data["violations"]
        print(f"Simulated violations: {len(sim_violations)}")
        for v in sim_violations:
            print(f"- Type: {v['type']} | Msg: {v['message']}")
        assert len(sim_violations) == 1
        assert sim_violations[0]["type"] == "single_position_cap"
        assert sim_violations[0]["ticker"] == "AMZN"
        print("TEST 7 SUCCESS: Compliance simulation sandbox correctly evaluated simulated weights without modifying the database.")

        # 13. File Ingestion Input Size & Magic Byte Security Validation
        print("\n--- TEST 8: PDF Header Check & Ingestion Hardening ---")
        # Create a mock text file (not starting with %PDF-)
        not_pdf_file = "fake_report.pdf"
        with open(not_pdf_file, "w") as f:
            f.write("This is a simple text file, not a valid PDF report.")
            
        try:
            with open(not_pdf_file, "rb") as f:
                bad_response = client.post(
                    "/documents/upload",
                    headers=auth_headers,
                    data={
                        "sector": "Energy",
                        "company": "Exxon",
                        "recommendation": "buy"
                    },
                    files={"file": ("fake_report.pdf", f, "application/pdf")}
                )
            assert bad_response.status_code == 400
            assert "Invalid PDF file signature." in bad_response.json()["detail"]
            print("TEST 8 SUCCESS: Input signature validation correctly blocked fake PDF uploads.")
        finally:
            if os.path.exists(not_pdf_file):
                os.remove(not_pdf_file)

        print("\n🎉 ALL PHASE 5 HARDENING AND RETRIEVAL TESTS PASSED! 🎉")

    finally:
        # Cleanup mock pdf
        if os.path.exists(tsla_thesis_file):
            os.remove(tsla_thesis_file)
            
        # Clean up uploads folder files
        upload_dir = settings.UPLOAD_DIR
        if os.path.exists(upload_dir):
            for file in os.listdir(upload_dir):
                file_path = os.path.join(upload_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

if __name__ == "__main__":
    test_governance_system()
