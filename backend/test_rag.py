import os
import sys
import uuid
import time
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
from app.db.session import SessionLocal
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
    # Insert text at coordinate (50, 100)
    page.insert_text((50, 100), content, fontsize=12)
    doc.save(filename)
    doc.close()
    print(f"Created mock PDF: {filename}")

def run_burst_worker():
    """Retrieves and executes all enqueued jobs synchronously for deterministic testing"""
    jobs = test_queue.get_jobs()
    print(f"\n[Worker] Found {len(jobs)} background tasks enqueued in test queue.")
    for job in jobs:
        print(f"[Worker] Running job {job.id} synchronously...")
        job.perform()
        test_queue.remove(job.id)

def test_rag_pipeline():
    app.api.endpoints.queue = test_queue
    test_queue.empty()

    # 1. Paths for mock files
    stetson_file = "stetson_report.pdf"
    uf_file = "uf_report.pdf"

    
    stetson_text = (
        "Stetson George Value Fund decided to hold a 5% allocation in Nvidia "
        "due to high AI growth conviction in 2024. The fund sector lead recommends "
        "accumulating shares at support levels."
    )
    uf_text = (
        "University of Florida Gator Growth Fund holds 12% in Apple and is heavily "
        "bullish on renewable energy sectors. The team sector lead is bullish on solar power."
    )
    
    try:
        create_test_pdf(stetson_file, stetson_text)
        create_test_pdf(uf_file, uf_text)

        # 2. Database Cleanup using Superuser connection (bypassing RLS)
        print("\n[DB] Cleaning up tables using superuser connection...")
        super_engine = create_engine("postgresql://civicpulse:civicpulse@localhost:5432/gripper")
        SuperSession = sessionmaker(bind=super_engine)
        with SuperSession() as s_db:
            s_db.query(models.DocumentChunk).delete()
            s_db.query(models.ResearchReport).delete()
            s_db.query(models.Institution).delete()
            
            stetson = models.Institution(name="Stetson University", slug="stetson")
            uf = models.Institution(name="University of Florida", slug="uf")
            s_db.add_all([stetson, uf])
            s_db.commit()
            
            stetson_id = str(stetson.id)
            uf_id = str(uf.id)
            print(f"Stetson Institution ID: {stetson_id}")
            print(f"UF Institution ID: {uf_id}")

        # 3. Register and Login users to obtain authentication tokens
        print("\n[Auth] Registering Stetson PM user...")
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

        with SuperSession() as s_db:
            stetson_user = s_db.query(models.User).filter(models.User.email == "analyst@stetson.edu").one()
            stetson_code = stetson_user.verification_code
        verify_response = client.post(
            "/auth/verify",
            json={"email": "analyst@stetson.edu", "code": stetson_code}
        )
        assert verify_response.status_code == 200
        
        print("[Auth] Logging in as Stetson user...")
        login_response = client.post(
            "/auth/login",
            headers={"X-Institution-ID": stetson_id},
            json={
                "email": "analyst@stetson.edu",
                "password": "stetson_secure_pwd"
            }
        )
        assert login_response.status_code == 200
        stetson_token = login_response.json()["access_token"]
        stetson_headers = {
            "Authorization": f"Bearer {stetson_token}",
            "X-Institution-ID": stetson_id
        }

        print("\n[Auth] Registering UF PM user...")
        reg_response = client.post(
            "/auth/register",
            headers={"X-Institution-ID": uf_id},
            json={
                "email": "analyst@uf.edu",
                "password": "uf_secure_pwd",
                "institution_id": uf_id,
                "role": "pm"
            }
        )
        assert reg_response.status_code == 201

        with SuperSession() as s_db:
            uf_user = s_db.query(models.User).filter(models.User.email == "analyst@uf.edu").one()
            uf_code = uf_user.verification_code
        verify_response = client.post(
            "/auth/verify",
            json={"email": "analyst@uf.edu", "code": uf_code}
        )
        assert verify_response.status_code == 200
        
        print("[Auth] Logging in as UF user...")
        login_response = client.post(
            "/auth/login",
            headers={"X-Institution-ID": uf_id},
            json={
                "email": "analyst@uf.edu",
                "password": "uf_secure_pwd"
            }
        )
        assert login_response.status_code == 200
        uf_token = login_response.json()["access_token"]
        uf_headers = {
            "Authorization": f"Bearer {uf_token}",
            "X-Institution-ID": uf_id
        }

        # 4. Upload Stetson Report
        print("\n[Upload] Uploading Stetson report...")
        with open(stetson_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                headers=stetson_headers,
                data={
                    "sector": "Technology",
                    "company": "NVIDIA (NVDA)",
                    "recommendation": "buy"
                },
                files={"file": (stetson_file, f, "application/pdf")}
            )
        assert response.status_code == 202
        stetson_report_id = response.json()["report_id"]
        print(f"Stetson report enqueued. ID: {stetson_report_id}")

        # 5. Upload UF Report
        print("\n[Upload] Uploading UF report...")
        with open(uf_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                headers=uf_headers,
                data={
                    "sector": "Technology",
                    "company": "Apple (AAPL)",
                    "recommendation": "buy"
                },
                files={"file": (uf_file, f, "application/pdf")}
            )
        assert response.status_code == 202
        uf_report_id = response.json()["report_id"]
        print(f"UF report enqueued. ID: {uf_report_id}")

        # 6. Run Worker to process jobs
        print("\n[Worker] Running background worker to process ingestion...")
        run_burst_worker()

        # 7. Check Ingestion Results
        with SuperSession() as s_db:
            # Stetson chunks count
            stetson_chunks = s_db.query(models.DocumentChunk).filter(models.DocumentChunk.institution_id == uuid.UUID(stetson_id)).all()
            print(f"\n[Verification] Stetson chunks stored in DB: {len(stetson_chunks)}")
            assert len(stetson_chunks) > 0
            
            # UF chunks count
            uf_chunks = s_db.query(models.DocumentChunk).filter(models.DocumentChunk.institution_id == uuid.UUID(uf_id)).all()
            print(f"[Verification] UF chunks stored in DB: {len(uf_chunks)}")
            assert len(uf_chunks) > 0

        # 8. TEST 1: Query as Stetson for Stetson content
        print("\n--- TEST 1: Semantic query as Stetson (Seeking NVIDIA info) ---")
        response = client.post(
            "/search/semantic",
            headers=stetson_headers,
            json={"query": "Nvidia 2024 allocation conviction", "limit": 3}
        )
        assert response.status_code == 200
        results = response.json()["results"]
        print(f"Query: 'Nvidia 2024 allocation conviction'")
        print(f"Results Count: {len(results)}")
        for r in results:
            print(f"- Chunk: '{r['content']}' (Similarity: {r['similarity']:.4f}, Company: {r['company']})")
        
        assert len(results) > 0
        assert "Nvidia" in results[0]["content"]
        assert results[0]["company"] == "NVIDIA (NVDA)"
        print("TEST 1 SUCCESS: Stetson successfully retrieved its own report.")

        # 9. TEST 2: Query as Stetson for UF content (should return NOTHING due to RLS)
        print("\n--- TEST 2: Semantic query as Stetson (Seeking UF Apple info) ---")
        response = client.post(
            "/search/semantic",
            headers=stetson_headers,
            json={"query": "bullish on renewable energy Apple solar power", "limit": 3}
        )
        assert response.status_code == 200
        results = response.json()["results"]
        print(f"Query: 'bullish on renewable energy Apple solar power'")
        print(f"Results Count: {len(results)}")
        for r in results:
            print(f"- Chunk: '{r['content']}' (Company: {r['company']})")
            
        # Assert that we DO NOT return the Apple report from the UF tenant
        assert all(r["company"] != "Apple (AAPL)" for r in results)
        print("TEST 2 SUCCESS: Stetson tenant cannot leak UF Apple/energy documents! RLS boundary verified.")

        # 10. TEST 3: Query as UF for UF content
        print("\n--- TEST 3: Semantic query as UF (Seeking Apple info) ---")
        response = client.post(
            "/search/semantic",
            headers=uf_headers,
            json={"query": "Apple and renewable energy solar power", "limit": 3}
        )
        assert response.status_code == 200
        results = response.json()["results"]
        print(f"Query: 'Apple and renewable energy solar power'")
        print(f"Results Count: {len(results)}")
        for r in results:
            print(f"- Chunk: '{r['content']}' (Similarity: {r['similarity']:.4f}, Company: {r['company']})")
        
        assert len(results) > 0
        assert "Apple" in results[0]["content"]
        assert results[0]["company"] == "Apple (AAPL)"
        print("TEST 3 SUCCESS: UF successfully retrieved its own report.")

        # 11. TEST 4: Query as UF for Stetson content (should return NOTHING)
        print("\n--- TEST 4: Semantic query as UF (Seeking Stetson NVIDIA info) ---")
        response = client.post(
            "/search/semantic",
            headers=uf_headers,
            json={"query": "Nvidia 2024 allocation", "limit": 3}
        )
        assert response.status_code == 200
        results = response.json()["results"]
        print(f"Query: 'Nvidia 2024 allocation'")
        print(f"Results Count: {len(results)}")
        for r in results:
            print(f"- Chunk: '{r['content']}' (Company: {r['company']})")
            
        # Assert that we DO NOT return the Nvidia report from the Stetson tenant
        assert all(r["company"] != "NVIDIA (NVDA)" for r in results)
        print("TEST 4 SUCCESS: UF tenant cannot leak Stetson Nvidia documents! RLS boundary verified.")

        print("\n🎉 ALL PHASE 2 RAG & RLS ISOLATION TESTS PASSED SUCCESSFULLY! 🎉")

    finally:
        # Cleanup local test files
        for f in [stetson_file, uf_file]:
            if os.path.exists(f):
                os.remove(f)
                
        # Clean up files in uploads directory
        # (Since we uploaded using TestClient, they are written to settings.UPLOAD_DIR)
        upload_dir = settings.UPLOAD_DIR
        if os.path.exists(upload_dir):
            for file in os.listdir(upload_dir):
                file_path = os.path.join(upload_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

if __name__ == "__main__":
    test_rag_pipeline()
