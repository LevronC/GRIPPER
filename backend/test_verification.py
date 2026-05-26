
import sys
import os
import uuid
import random
import string
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add root backend folder to path
sys.path.insert(0, os.path.realpath(os.path.dirname(__file__)))

from app.main import app
from app import models

client = TestClient(app)

def test_verification_flow():
    print("\n--- TEST: .edu Restriction and Verification Flow ---")
    
    # Setup database connection
    DATABASE_URL = "postgresql://gripper_app:gripper_secure@localhost:5432/gripper"
    SUPER_DATABASE_URL = "postgresql://civicpulse:civicpulse@localhost:5432/gripper"
    super_engine = create_engine(SUPER_DATABASE_URL)
    SuperSession = sessionmaker(bind=super_engine)
    
    # 1. Setup institution
    with SuperSession() as db:
        inst = db.query(models.Institution).filter(models.Institution.slug == "test_edu").first()
        if not inst:
            inst = models.Institution(id=uuid.uuid4(), name="Test Edu Univ", slug="test_edu")
            db.add(inst)
            db.commit()
            db.refresh(inst)
        institution_id = inst.id

    # 2. Try registering with non-edu email (should FAIL)
    print("Testing non-edu email restriction...")
    bad_reg = {
        "email": "student@gmail.com",
        "password": "password123",
        "institution_id": str(institution_id),
        "role": "analyst"
    }
    response = client.post("/auth/register", json=bad_reg)
    assert response.status_code == 422
    print("SUCCESS: Non-edu email was rejected.")

    # 3. Register with valid .edu email
    print("Registering with valid .edu email...")
    edu_email = f"student_{''.join(random.choices(string.ascii_lowercase, k=5))}@stetson.edu"
    good_reg = {
        "email": edu_email,
        "password": "password123",
        "institution_id": str(institution_id),
        "role": "analyst"
    }
    response = client.post("/auth/register", json=good_reg)
    assert response.status_code == 201
    print(f"SUCCESS: User {edu_email} registered.")

    # 4. Try logging in before verification (should FAIL)
    print("Testing login before verification...")
    login_data = {"email": edu_email, "password": "password123"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 403
    assert "not verified" in response.json()["detail"].lower()
    print("SUCCESS: Login blocked for unverified user.")

    # 5. Fetch verification code from DB (as a real user would check their email)
    print("Fetching verification code from DB...")
    with SuperSession() as db:
        user = db.query(models.User).filter(models.User.email == edu_email).one()
        v_code = user.verification_code
    assert v_code is not None
    print(f"Code found: {v_code}")

    # 6. Verify with WRONG code (should FAIL)
    print("Testing verification with wrong code...")
    response = client.post("/auth/verify", json={"email": edu_email, "code": "000000"})
    assert response.status_code == 400
    print("SUCCESS: Wrong code was rejected.")

    # 7. Verify with CORRECT code
    print("Testing verification with correct code...")
    response = client.post("/auth/verify", json={"email": edu_email, "code": v_code})
    assert response.status_code == 200
    print("SUCCESS: Email verified.")

    # 8. Login after verification (should SUCCEED)
    print("Testing login after verification...")
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()
    print("SUCCESS: Login successful for verified user.")

    print("\n🎉 ALL VERIFICATION FLOW TESTS PASSED! 🎉")

if __name__ == "__main__":
    try:
        test_verification_flow()
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
