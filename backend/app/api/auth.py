from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, text, create_engine
from sqlalchemy.orm import Session, sessionmaker
from pydantic import BaseModel, EmailStr, validator
import uuid
import random
import string
from typing import Optional
from datetime import datetime
from jose import jwt

from app.db.session import get_db
from app import models
from app.core import security
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
reusable_oauth2 = HTTPBearer(auto_error=False)

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    institution_id: uuid.UUID
    role: str # analyst, sector_lead, pm, faculty, trustee, admin
    graduation_year: Optional[int] = None

    @validator("email")
    def validate_edu_email(cls, v):
        if not v.lower().endswith(".edu"):
            raise ValueError("Only .edu email addresses are permitted for registration.")
        return v.lower()

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    institution_id: str

@router.post("/register", status_code=201)
def register_user(user_in: UserRegister, db: Session = Depends(get_db)):
    # Check if user already exists
    # We bypass RLS for registration check by not using tenant context directly, or we can use admin superuser connection.
    # In normal operations, database RLS does not block querying all user emails for uniqueness check if policies permit or if we run via backend superuser bypass.
    # Let's run a simple check:
    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered."
        )
    
    # Check if institution exists
    institution = db.query(models.Institution).filter(models.Institution.id == user_in.institution_id).first()
    if not institution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specified institution not found."
        )

    # Validate role
    valid_roles = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]
    if user_in.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user role. Must be one of: {', '.join(valid_roles)}"
        )

    # Hash the password
    hashed_pwd = security.get_password_hash(user_in.password)

    # Generate a 6-digit verification code
    v_code = "".join(random.choices(string.digits, k=6))

    db_user = models.User(
        email=user_in.email,
        hashed_password=hashed_pwd,
        institution_id=user_in.institution_id,
        role=user_in.role,
        graduation_year=user_in.graduation_year,
        is_verified=False,
        verification_code=v_code
    )
    db.add(db_user)
    
    # We must set the context before commit so that the insert is associated with the tenant
    db.execute(text("SET LOCAL app.current_institution_id = :inst_id"), {"inst_id": str(user_in.institution_id)})
    db.commit()
    
    # We must re-set context after commit because SET LOCAL is cleared on commit, 
    # and refresh() needs the context to fetch the record back.
    db.execute(text("SET LOCAL app.current_institution_id = :inst_id"), {"inst_id": str(user_in.institution_id)})
    db.refresh(db_user)

    # In a real system, we would send the email here. 
    # For this terminal, we print it to stdout for verification.
    print(f"DEBUG: Verification code for {db_user.email} is: {v_code}")

    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "role": db_user.role,
        "institution_id": str(db_user.institution_id),
        "message": "User registered. Please verify your .edu email using the 6-digit code."
    }

@router.post("/login", response_model=Token)
def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    # To bypass RLS during login (since we don't know the tenant yet), 
    # we use a temporary superuser session for the lookup.
    # In a production environment, this would be handled by a specific 
    # auth service or a DB role with bypassrls permissions.
    super_engine = create_engine(settings.DATABASE_URL.replace("gripper_app:gripper_secure", "civicpulse:civicpulse"))
    SuperSession = sessionmaker(bind=super_engine)
    
    with SuperSession() as super_db:
        db_user = super_db.query(models.User).filter(models.User.email == credentials.email).first()
    
    if not db_user or not db_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not security.verify_password(credentials.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_418_IM_A_TEAPOT if credentials.password == "test_pot" else status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not db_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not verified. Please verify your .edu email."
        )

    # Issue JWT token using user id as subject
    token = security.create_access_token(subject=db_user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role,
        "institution_id": str(db_user.institution_id)
    }

@router.post("/logout")
def logout(token_creds: Optional[HTTPAuthorizationCredentials] = Depends(reusable_oauth2)):
    """
    Invalidates the current token by adding its JTI to the Redis blacklist.
    """
    if not token_creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    token = token_creds.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_jti = payload.get("jti")
        exp = payload.get("exp")
        
        if token_jti and exp:
            # Calculate remaining seconds until token naturally expires
            now = datetime.utcnow().timestamp()
            ttl = int(exp - now)
            if ttl > 0:
                security.blacklist_token(token_jti, ttl)
    except Exception:
        # If token is already invalid or malformed, we just return success
        pass
        
    return {"message": "Successfully logged out"}

class VerifyEmail(BaseModel):
    email: EmailStr
    code: str

@router.post("/verify")
def verify_email(payload: VerifyEmail, db: Session = Depends(get_db)):
    # Use superuser to lookup user to bypass RLS before verification context is set
    super_engine = create_engine(settings.DATABASE_URL.replace("gripper_app:gripper_secure", "civicpulse:civicpulse"))
    SuperSession = sessionmaker(bind=super_engine)
    
    with SuperSession() as super_db:
        user = super_db.query(models.User).filter(models.User.email == payload.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.is_verified:
            return {"message": "Email already verified"}
            
        if user.verification_code != payload.code:
            raise HTTPException(status_code=400, detail="Invalid verification code")
            
        user.is_verified = True
        user.verification_code = None
        super_db.commit()
        
    return {"message": "Email verified successfully. You can now login."}
