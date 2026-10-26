import os

DATABASE_URL = os.getenv("MONEYFX_DATABASE_URL", "sqlite:///./moneyfx.db")
SECRET_KEY = os.getenv("MONEYFX_SECRET_KEY", "dev-secret-change-me")
ACCESS_TOKEN_MINUTES = int(os.getenv("MONEYFX_TOKEN_MINUTES", "720"))
CORS_ORIGINS = os.getenv("MONEYFX_CORS_ORIGINS", "http://localhost:5173").split(",")
BASE_CURRENCY = "USD"
MAX_DEPOSIT = 1_000_000
BACKGROUND_WORKERS = os.getenv("MONEYFX_BACKGROUND_WORKERS", "1") == "1"  # limit-order matcher and bot runner
