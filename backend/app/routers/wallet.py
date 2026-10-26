import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import MAX_DEPOSIT
from ..database import get_db
from ..security import get_account
from ..trading import cash_wallet

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("", response_model=schemas.WalletOut)
def get_wallet(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    return cash_wallet(db, account)


@router.post("/deposit", response_model=schemas.TransactionOut, status_code=201)
def deposit(body: schemas.MoneyIn, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    # Mock payment rail: every deposit succeeds instantly. Swap in a PSP (Stripe, M-Pesa, ...) here.
    if body.amount > MAX_DEPOSIT:
        raise HTTPException(400, f"Maximum single deposit is {MAX_DEPOSIT:,} USD")
    wallet = cash_wallet(db, account)
    wallet.balance += body.amount
    txn = models.Transaction(wallet_id=wallet.id, type="deposit", amount=body.amount, balance_after=wallet.balance,
                             method=body.method, reference=f"DEP-{uuid.uuid4().hex[:10].upper()}")
    db.add(txn)
    db.commit()
    return txn


@router.post("/withdraw", response_model=schemas.TransactionOut, status_code=201)
def withdraw(body: schemas.MoneyIn, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    wallet = cash_wallet(db, account)
    if body.amount > wallet.available:
        raise HTTPException(400, f"Insufficient available balance ({wallet.available:.2f} USD)")
    wallet.balance -= body.amount
    txn = models.Transaction(wallet_id=wallet.id, type="withdrawal", amount=-body.amount,
                             balance_after=wallet.balance, method=body.method,
                             reference=f"WDR-{uuid.uuid4().hex[:10].upper()}")
    db.add(txn)
    db.commit()
    return txn


@router.get("/transactions", response_model=list[schemas.TransactionOut])
def transactions(limit: int = 50, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    wallet = cash_wallet(db, account)
    return db.scalars(select(models.Transaction).where(models.Transaction.wallet_id == wallet.id)
                      .order_by(models.Transaction.id.desc()).limit(min(limit, 500))).all()
