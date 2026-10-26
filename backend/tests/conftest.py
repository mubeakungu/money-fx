import os
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["MONEYFX_DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["MONEYFX_BACKGROUND_WORKERS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def user(client):
    import uuid
    r = client.post("/api/auth/register", json={"email": f"{uuid.uuid4().hex[:8]}@example.com",
                                                "password": "s3cret-pass", "full_name": "Test Trader"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
