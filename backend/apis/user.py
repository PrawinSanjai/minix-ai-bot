from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from models import User
from database import get_db
from services.auth import Auth_Service
from services.user import User_Service

user_service = User_Service()

auth_service = Auth_Service()
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=schemas.UserOut)
def get_profile(user: User = Depends(auth_service.get_current_user)):
    return user


@router.put("/me", response_model=schemas.UserOut)
def update_profile_route(
    payload: schemas.UserUpdate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.update_profile(db, user, payload)


@router.put("/me/tone", response_model=schemas.UserOut)
def update_tone_route(
    payload: schemas.ToneUpdate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.update_tone(db, user, payload)


@router.post("/change-password")
def change_password_route(
    payload: schemas.ChangePasswordRequest,
    user: User = Depends(auth_service.get_current_user),
):
    return auth_service.change_password(
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        user=user,
    )
