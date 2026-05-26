from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
import uuid
from typing import Optional

from app.db.session import get_db
from app import models
from app.core import security

router = APIRouter(prefix="/auth", tags=["auth"])

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    institution_id: uuid.UUID
    role: str # analyst, sector_lead, pm, faculty, trustee, admin
    graduation_year: Optional[int] = None

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

    db_user = models.User(
        email=user_in.email,
        hashed_password=hashed_pwd,
        institution_id=user_in.institution_id,
        role=user_in.role,
        graduation_year=user_in.graduation_year
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "role": db_user.role,
        "institution_id": str(db_user.institution_id)
    }

@router.post("/login", response_model=Token)
def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == credentials.email).first()
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

    # Issue JWT token using user id as subject
    token = security.create_access_token(subject=db_user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role,
        "institution_id": str(db_user.institution_id)
    }
