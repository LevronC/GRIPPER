from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from typing import Optional, List

from app.core.config import settings
from app.db.session import get_db
from app import models

reusable_oauth2 = HTTPBearer(auto_error=False)

def get_current_user(
    db: Session = Depends(get_db),
    token_creds: Optional[HTTPAuthorizationCredentials] = Depends(reusable_oauth2),
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-ID")
) -> Optional[models.User]:
    """
    Dependency to get the current authenticated user and enforce the session-scoped
    PostgreSQL Row-Level Security (RLS) context using the user's institution ID.
    If no token is supplied, it falls back to the X-Institution-ID header to preserve
    compatibility for existing tests/scripts.
    """
    if token_creds:
        token = token_creds.credentials
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials: sub claim missing",
                )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials: JWT invalid or expired",
            )
        
        user = db.query(models.User).filter(models.User.id == uuid.UUID(user_id)).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        # Enforce Postgres session-scoped RLS context using the user's bound institution
        db.execute(text("SET app.current_institution_id = :inst_id"), {"inst_id": str(user.institution_id)})
        return user
    
    # Fallback to header if no token credentials are provided (for backward compatibility)
    if x_institution_id:
        try:
            # Validate UUID format
            uuid.UUID(x_institution_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Institution-ID UUID format"
            )
        db.execute(text("SET app.current_institution_id = :inst_id"), {"inst_id": x_institution_id})
        return None
    
    return None

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Optional[models.User] = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for this operation."
            )
        
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {self.allowed_roles}. Current role: {current_user.role}"
            )
        return current_user
