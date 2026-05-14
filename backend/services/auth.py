import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.api_key import APIKeyHeader
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext

from database import db_session
from config import Configuration
from models import (
    User
)

config = Configuration()

SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


class AuthService:
    def _ensure_secret_key(self):
        if not SECRET_KEY or len(SECRET_KEY) < 32:
            raise HTTPException(
                status_code=500,
                detail="JWT secret is not configured securely"
            )

    def hash_password(self, password: str):
        return pwd_context.hash(password)

    def verify_password(self, plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, data: dict):
        self._ensure_secret_key()
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    def register_user(self, user):
        role = user.role.lower()
        if role != "patient":
            raise HTTPException(status_code=403, detail="Only patients can self-register")

        with db_session() as db:
            existing_user = db.query(User).filter(User.email == user.email.lower()).first()

            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")

            hashed_pw = self.hash_password(user.password)

            new_user = User(
                name=user.name,
                email=user.email.lower(),
                hashed_password=hashed_pw,
                role=role,
                is_active=True
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
        return {"message": "User created successfully"}

    def login(self, user):
        with db_session() as db:
            db_user = db.query(User).filter(
                User.email == user.username.lower()
            ).first()

            if not db_user or not self.verify_password(
                user.password,
                db_user.hashed_password
            ):
                raise CREDENTIALS_EXCEPTION

            if not db_user.is_active:
                raise HTTPException(403, "Account deactivated")

            access_token = self.create_access_token(
                data={"sub": str(db_user.id), "role": db_user.role}
            )

            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
            
    def logout(self):
        return {"message": "Logged out successfully"}
        
    def change_password(self, current_password: str, new_password: str, confirm_password: str, user: User):
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="New password and confirmation do not match")

        if not self.verify_password(current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        if self.verify_password(new_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="New password must be different from current password")
        
        new_hash_password = self.hash_password(new_password)
        with db_session() as db:
            current_user = db.query(User).filter(User.email==user.email).first()
            current_user.hashed_password = new_hash_password
            db.commit()
            
        return {"message": "Password changed successfully"}

def get_current_user(token: str = Depends(oauth2_scheme)):
    AuthService()._ensure_secret_key()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not user_id:
        raise CREDENTIALS_EXCEPTION

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise CREDENTIALS_EXCEPTION

    with db_session() as db:
        user = db.query(User).filter(
            User.id == user_id
        ).first()

        if not user:
            raise CREDENTIALS_EXCEPTION
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated")

        return user


def require_role(required_role: str):
    def role_checker(user: User = Depends(get_current_user)):
        user_role = user.role.lower()
        # if required_role not in VALID_ROLES:
        #     raise HTTPException(status_code=500, detail="Invalid role guard")

        if user_role == "admin":
            return user

        if user_role != required_role.lower():
            raise HTTPException(status_code=403, detail="Access denied")

        return user

    return role_checker


def verify_api_key(api_key: str = Depends(api_key_header)):
    expected_api_key = config.HOSTECH_API_KEY
    if not expected_api_key or expected_api_key == "None":
        raise HTTPException(status_code=500, detail="API key is not configured")

    if not api_key or not secrets.compare_digest(api_key, expected_api_key):
        raise CREDENTIALS_EXCEPTION
    return api_key
