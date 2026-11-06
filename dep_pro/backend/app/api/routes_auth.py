from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class MeOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    section_id: int | None
    department_id: int | None


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="بيانات الدخول غير صحيحة")
    token = create_access_token(str(user.id), {"role": user.role.value})
    return TokenOut(access_token=token, role=user.role.value)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.value,
        section_id=user.section_id,
        department_id=user.department_id,
    )