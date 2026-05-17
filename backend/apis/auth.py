from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.auth import Auth_Service
from schemas import UserRegister, UserLogin

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = Auth_Service()

@router.post("/register")
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return auth_service.register_user(payload, db)


@router.post("/login")
def login_route(payload: UserLogin, db: Session = Depends(get_db)):
    return auth_service.login(payload, db)
