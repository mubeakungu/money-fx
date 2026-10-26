import os

DATABASE_URL = os.getenv("MONEYFX_DATABASE_URL", "sqlite:///./moneyfx.db")
SECRET_KEY = os.getenv("MONEYFX_SECRET_KEY", "dev-secret-change-me")
if os.getenv("MONEYFX_ENV") == "production" and SECRET_KEY == "dev-secret-change-me":
    raise RuntimeError("Set MONEYFX_SECRET_KEY before running in production")
ACCESS_TOKEN_MINUTES = int(os.getenv("MONEYFX_TOKEN_MINUTES", "720"))
CORS_ORIGINS = os.getenv("MONEYFX_CORS_ORIGINS", "http://localhost:5173").split(",")
BASE_CURRENCY = "USD"
MAX_DEPOSIT = 1_000_000
STATIC_DIR = os.getenv("MONEYFX_STATIC_DIR")  # built frontend to serve, e.g. frontend/dist
BACKGROUND_WORKERS = os.getenv("MONEYFX_BACKGROUND_WORKERS", "1") == "1"  # limit-order matcher and bot runner
# Only these users may run bots on the OANDA account configured above (comma-separated emails).
# Empty means nobody can, so a public deployment never lets strangers trade your account.
OANDA_OWNER_EMAILS = {e.strip().lower() for e in os.getenv("OANDA_OWNER_EMAILS", "").split(",") if e.strip()}
