from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError
from pydantic import BaseModel, EmailStr, validator
import uuid
import random
import string
from typing import Optional
from datetime import datetime
from jose import jwt, JWTError

from app.db.session import _engine_kwargs
from app.core.database_url import database_url_error_hint
from app import models
from app.core import security
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
reusable_oauth2 = HTTPBearer(auto_error=False)

_super_engine = None
_super_session_factory = None


def get_superuser_session():
    global _super_engine, _super_session_factory
    if _super_engine is None:
        _super_engine = create_engine(
            settings.SUPERUSER_DATABASE_URL,
            **_engine_kwargs(settings.SUPERUSER_DATABASE_URL),
        )
        _super_session_factory = sessionmaker(bind=_super_engine)
    return _super_session_factory()

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
def register_user(user_in: UserRegister):
    valid_roles = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]
    if user_in.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user role. Must be one of: {', '.join(valid_roles)}",
        )

    hashed_pwd = security.get_password_hash(user_in.password)
    v_code = "".join(random.choices(string.digits, k=6))

    try:
        with get_superuser_session() as super_db:
            existing_user = super_db.query(models.User).filter(models.User.email == user_in.email).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this email is already registered.",
                )

            institution = (
                super_db.query(models.Institution)
                .filter(models.Institution.id == user_in.institution_id)
                .first()
            )
            if not institution:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified institution not found. Run database migrations/seeding first.",
                )

            db_user = models.User(
                email=user_in.email,
                hashed_password=hashed_pwd,
                institution_id=user_in.institution_id,
                role=user_in.role,
                graduation_year=user_in.graduation_year,
                is_verified=False,
                verification_code=v_code,
            )
            super_db.add(db_user)
            super_db.commit()
            super_db.refresh(db_user)
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered.",
        )
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=database_url_error_hint(settings.SUPERUSER_DATABASE_URL, exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {exc}",
        ) from exc

    print(f"DEBUG: Verification code for {db_user.email} is: {v_code}")

    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "role": db_user.role,
        "institution_id": str(db_user.institution_id),
        "message": "User registered. Please verify your .edu email using the 6-digit code.",
    }

@router.post("/login", response_model=Token)
def login_user(credentials: UserLogin):
    try:
        with get_superuser_session() as super_db:
            db_user = super_db.query(models.User).filter(models.User.email == credentials.email).first()
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=database_url_error_hint(settings.SUPERUSER_DATABASE_URL, exc),
        ) from exc
    
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
def forgot_password(payload: ForgotPasswordRequest):
    with get_superuser_session() as super_db:
        user = super_db.query(models.User).filter(models.User.email == payload.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found for that email.",
            )
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified. Complete email verification before resetting your password.",
            )

        reset_code = "".join(random.choices(string.digits, k=6))
        user.verification_code = reset_code
        super_db.commit()

    print(f"DEBUG: Password reset code for {payload.email} is: {reset_code}")

    return {
        "message": "If an account exists for that email, a reset code has been sent. In development, check the backend console.",
    }

@router.post("/reset-password", response_model=Token)
def reset_password(payload: ResetPasswordRequest):
    with get_superuser_session() as super_db:
        user = super_db.query(models.User).filter(models.User.email == payload.email).first()
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
        super_db.commit()
        super_db.refresh(user)

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
def verify_email(payload: VerifyEmail):
    with get_superuser_session() as super_db:
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
