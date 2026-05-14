from fastapi import APIRouter, Depends
from datetime import datetime

import models
import schemas
from database import db_session
from services import auth

router = APIRouter()
auth_service = auth.AuthService()

@router.get("/health")
def health_check():
    return {
        "time": datetime.now(),
        "result": "success"
    }

@router.get("/me", response_model=schemas.UserOut)
def get_user_profile(user = Depends(auth.get_current_user)):
    profile_id = None
    with db_session() as db:
        role = user.role.lower()
        if role == "patient":
            profile = db.query(models.Patient).filter(models.Patient.user_id == user.id).first()
            profile_id = profile.id if profile else None
        elif role == "doctor":
            profile = db.query(models.Doctor).filter(models.Doctor.user_id == user.id).first()
            profile_id = profile.id if profile else None

    return schemas.UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        profile_id=profile_id,
    )

@router.post("/change-password")
def change_password(payload: schemas.ChangePasswordRequest, user = Depends(auth.get_current_user)):
    return auth_service.change_password(
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
    )

@router.post("/logout")
def logout(user = Depends(auth.get_current_user)):
    return auth_service.logout()