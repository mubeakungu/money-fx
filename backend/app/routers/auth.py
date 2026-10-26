from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import BASE_CURRENCY
from ..database import get_db
from ..security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(id=user.id, email=user.email, full_name=user.full_name, country=user.country,
                           created_at=user.created_at, account_id=user.account.id,
                           account_status=user.account.status)


def _authenticate(db: Session, email: str, password: str) -> models.User:
    user = db.scalars(select(models.User).where(models.User.email == email.lower())).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return user


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalars(select(models.User).where(models.User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = models.User(email=email, password_hash=hash_password(body.password),
                       full_name=body.full_name.strip(), country=body.country and body.country.upper())
    account = models.Account(user=user, base_currency=BASE_CURRENCY)
    db.add_all([user, account, models.Wallet(account=account, currency=BASE_CURRENCY,
                                              balance=Decimal(0), locked=Decimal(0))])
    db.commit()
    return schemas.TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    return schemas.TokenOut(access_token=create_token(_authenticate(db, body.email, body.password).id))


@router.post("/token", response_model=schemas.TokenOut, include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 form login so the Swagger UI "Authorize" button works."""
    return schemas.TokenOut(access_token=create_token(_authenticate(db, form.username, form.password).id))


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user_out(user)


@router.patch("/me", response_model=schemas.UserOut)
def update_me(body: schemas.UserUpdate, user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.country is not None:
        user.country = body.country.upper()
    db.commit()
    return user_out(user)


@router.post("/change-password", status_code=204)
def change_password(body: schemas.PasswordChange, user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
