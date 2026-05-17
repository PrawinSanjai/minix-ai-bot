from sqlalchemy.orm import Session
from models import User
from schemas import UserUpdate, ToneUpdate


class User_Service():
    def update_profile(self, db: Session, user: User, payload: UserUpdate) -> User:
        if payload.name is not None:
            user.name = payload.name
            db.commit()
            db.refresh(user)
        return user


    def update_tone(self, db: Session, user: User, payload: ToneUpdate) -> User:
        user.tone = payload.tone
        db.commit()
        db.refresh(user)
        return user
