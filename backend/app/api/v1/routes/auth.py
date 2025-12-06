from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserRead
from app.services.email import EmailService
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
email_service = EmailService()


class VerifyRequest(BaseModel):
    token: str


@router.post("/register", response_model=UserRead)
def register(user_in: UserCreate, db: Session = Depends(deps.get_db_session)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    verification_token = secrets.token_urlsafe(32)
    db_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        verification_token=verification_token,
        verification_sent_at=datetime.utcnow(),
        is_verified=False,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    email_service.send_verification_email(db_user.email, verification_token)
    return db_user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(deps.get_db_session)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")
    access_token = create_access_token(subject=str(user.id), expires_delta=timedelta(minutes=settings.access_token_expire_minutes))
    return Token(access_token=access_token)


@router.post("/verify")
def verify_account(payload: VerifyRequest, db: Session = Depends(deps.get_db_session)):
    user = db.query(User).filter(User.verification_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid verification token")
    user.is_verified = True
    user.verification_token = None
    user.verification_sent_at = None
    db.commit()
    return {"detail": "Account verified"}
