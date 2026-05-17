from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import schemas
from services.auth import AuthService, get_current_user
from models import User

router = APIRouter(prefix="/api/users", tags=["users"])
auth_service = AuthService()


@router.get("/me", response_model=schemas.UserOut)
def get_profile(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=schemas.UserOut)
def update_profile(
    payload: schemas.UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.name is not None:
        user.name = payload.name
        db.commit()
        db.refresh(user)
    return user


@router.put("/me/tone", response_model=schemas.UserOut)
def update_tone(
    payload: schemas.ToneUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.tone = payload.tone
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(
    payload: schemas.ChangePasswordRequest,
    user: User = Depends(get_current_user),
):
    return auth_service.change_password(
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
    )
