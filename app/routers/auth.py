from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from datetime import datetime
import os

from app.database import get_db
from app.models.user import User
from app.schemas import UserCreate, Token
from app.utils.security import hash_password, verify_password
from app.utils.jwt import create_access_token, oauth2_scheme, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=Token)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        account_type=user.account_type,
        company_name=user.company_name,
        access_level=user.access_level,
        full_name=user.full_name,


    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    token = create_access_token({"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


# ✅ USED BY QA ROUTER
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    return user


@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "full_name": current_user.full_name,
        "account_type": current_user.account_type,
    }
