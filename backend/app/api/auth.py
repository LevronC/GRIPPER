from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, validator
import uuid
import random
import string
from typing import Optional
from datetime import datetime
import jwt

import logging

from app.api.deps import resolve_user_by_email
from app.db.session import get_db, set_tenant
from app import models
from app.core import security
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
reusable_oauth2 = HTTPBearer(auto_error=False)

# Roles a user may select at self-registration.
# Privileged roles (pm, trustee, admin) must be assigned by an existing admin
# via PATCH /users/{user_id}/role — they cannot be self-claimed.
SELF_REGISTRATION_ROLES = ["analyst", "sector_lead", "faculty"]
ALL_ROLES = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]


def _load_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """
    Resolve the user's institution through the SECURITY DEFINER lookup, bind the
    session to it, then read the full row under RLS. No RLS-bypassing connection.
    """
    resolved = resolve_user_by_email(db, email)
    if not resolved:
        return None
    user_id, institution_id = resolved
    set_tenant(db, institution_id)
    return db.execute(select(models.User).where(models.User.id == user_id)).scalar_one_or_none()

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
    user_id: str
    email: str
    graduation_year: Optional[int] = None

@router.post("/register", status_code=201)
def register_user(user_in: UserRegister, db: Session = Depends(get_db)):
    if user_in.role not in SELF_REGISTRATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Self-registration is limited to: {', '.join(SELF_REGISTRATION_ROLES)}. "
                "Contact your institution administrator to be assigned a privileged role."
            ),
        )
    if resolve_user_by_email(db, user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered.",
        )
    institution = db.get(models.Institution, user_in.institution_id)
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specified institution not found.")

    v_code = "".join(random.choices(string.digits, k=6))
    set_tenant(db, institution.id)
    db_user = models.User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        institution_id=institution.id,
        role=user_in.role,
        graduation_year=user_in.graduation_year,
        is_verified=False,
        verification_code=v_code,
    )
    db.add(db_user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered.",
        )

    if settings.DEBUG_PRINT_CODES:
        logger.warning(
            "DEBUG_PRINT_CODES enabled — verification code for %s: %s — DISABLE IN PRODUCTION",
            db_user.email, v_code,
        )
    else:
        logger.info("Verification code issued for %s (code suppressed)", db_user.email)

    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "role": db_user.role,
        "institution_id": str(db_user.institution_id),
        "message": "User registered. Please verify your .edu email using the 6-digit code.",
    }

@router.post("/login", response_model=Token)
def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    db_user = _load_user_by_email(db, credentials.email)

    if not db_user or not db_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not security.verify_password(credentials.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
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
        "institution_id": str(db_user.institution_id),
        "user_id": str(db_user.id),
        "email": db_user.email,
        "graduation_year": db_user.graduation_year,
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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @validator("email")
    def normalize_email(cls, v):
        return v.lower()

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

    @validator("email")
    def normalize_email(cls, v):
        return v.lower()

    @validator("new_password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    reset_code = None
    user = _load_user_by_email(db, payload.email)
    # Do not reveal whether the email exists — always return the same response.
    if user and user.is_verified:
        reset_code = "".join(random.choices(string.digits, k=6))
        user.verification_code = reset_code

    if reset_code:
        if settings.DEBUG_PRINT_CODES:
            logger.warning(
                "DEBUG_PRINT_CODES enabled — reset code for %s: %s — DISABLE IN PRODUCTION",
                payload.email, reset_code,
            )
        else:
            logger.info("Password reset code issued for %s (code suppressed)", payload.email)

    return {
        "message": "If an account exists for that email, a reset code has been sent.",
    }

@router.post("/reset-password", response_model=Token)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    if True:
        user = _load_user_by_email(db, payload.email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified. Complete email verification first.",
            )
        if not user.verification_code or user.verification_code != payload.code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code.")

        user.hashed_password = security.get_password_hash(payload.new_password)
        user.verification_code = None
        db.flush()

        token = security.create_access_token(subject=user.id)
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role,
            "institution_id": str(user.institution_id),
            "user_id": str(user.id),
            "email": user.email,
            "graduation_year": user.graduation_year,
        }

@router.post("/verify")
def verify_email(payload: VerifyEmail, db: Session = Depends(get_db)):
    if True:
        user = _load_user_by_email(db, payload.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.is_verified:
            return {"message": "Email already verified"}
            
        if user.verification_code != payload.code:
            raise HTTPException(status_code=400, detail="Invalid verification code")
            
        user.is_verified = True
        user.verification_code = None
        
    return {"message": "Email verified successfully. You can now login."}
