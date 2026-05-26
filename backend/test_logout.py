
import sys
import os
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add root backend folder to path
sys.path.insert(0, os.path.realpath(os.path.dirname(__file__)))

from app.main import app
from app.db.session import get_db
from app import models

client = TestClient(app)

def test_logout_revocation():
    print("\n--- TEST: Logout and Token Revocation ---")
    
    # 1. Setup: Create a test institution and user
    DATABASE_URL = "postgresql://gripper_app:gripper_secure@localhost:5432/gripper"
    SUPER_DATABASE_URL = "postgresql://civicpulse:civicpulse@localhost:5432/gripper"
    engine = create_engine(DATABASE_URL)
    super_engine = create_engine(SUPER_DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    SuperSession = sessionmaker(bind=super_engine)
    
    with SuperSession() as db:
        # Cleanup using superuser to bypass RLS
        db.query(models.User).filter(models.User.email == "logout_test@stetson.edu").delete()
        inst = db.query(models.Institution).filter(models.Institution.slug == "test_inst").first()
        if not inst:
            inst = models.Institution(id=uuid.uuid4(), name="Test Institution", slug="test_inst")
            db.add(inst)
        db.commit()
        
        # Fetch it back to get the ID if it already existed
        inst = db.query(models.Institution).filter(models.Institution.slug == "test_inst").one()
        institution_id = inst.id

    # 2. Register
    reg_data = {
        "email": "logout_test@stetson.edu",
        "password": "testpassword123",
        "institution_id": str(institution_id),
        "role": "analyst"
    }
    response = client.post("/auth/register", json=reg_data)
    assert response.status_code == 201
    print("User registered.")

    with SuperSession() as db:
        user = db.query(models.User).filter(models.User.email == "logout_test@stetson.edu").one()
        verification_code = user.verification_code
    response = client.post("/auth/verify", json={"email": "logout_test@stetson.edu", "code": verification_code})
    assert response.status_code == 200
    print("User verified.")

    # 3. Login
    login_data = {"email": "logout_test@stetson.edu", "password": "testpassword123"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    print("User logged in, token acquired.")

    # 4. Verify token works
    response = client.get("/health")
    print(f"Health check status: {response.status_code}")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/portfolios", headers=headers)
    print(f"Portfolios check status: {response.status_code}")
    assert response.status_code == 200
    print("Token verified: Authorized access works (checked /portfolios).")

    # 5. Logout
    response = client.post("/auth/logout", headers=headers)
    assert response.status_code == 200
    print("User logged out.")

    # 6. Verify token is now invalid
    response = client.get("/portfolios", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has been revoked"
    print("Token verified: Revoked token correctly rejected with 401.")

    print("🎉 LOGOUT REVOCATION TEST PASSED! 🎉")

if __name__ == "__main__":
    try:
        test_logout_revocation()
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
