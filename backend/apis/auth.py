from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import UserRegister, UserLogin, TokenOut
from services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_service = AuthService()


@router.post("/register")
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return auth_service.register_user(payload, db)


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    return auth_service.login(payload, db)
