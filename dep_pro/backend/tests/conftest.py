"""
إعداد بيئة الاختبار: قاعدة SQLite مؤقتة معزولة، ومُضمِّن حتمي، وبلا Redis.
يجب ضبط المتغيرات قبل استيراد أي وحدة من التطبيق، لأن الإعدادات تُقرأ عند الاستيراد.
"""

import os
import tempfile
from datetime import datetime, timezone

_TMP_DIR = tempfile.mkdtemp(prefix="sdp_tests_")
os.environ["APP_ENV"] = "development"
os.environ["EMBEDDING_PROVIDER"] = "stub"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'test.db')}"
os.environ["STORAGE_DIR"] = os.path.join(_TMP_DIR, "materials")
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-tests"
os.environ.pop("OPENAI_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.seed_db import seed  # noqa: E402

PASSWORD = "ChangeMe123!"
ACCOUNTS = {
    "student": "student@sdp.local",
    "rep": "rep@sdp.local",
    "instructor": "dr@sdp.local",
    "coord": "coord@sdp.local",
    "head": "head@sdp.local",
}


@pytest.fixture(scope="session")
def client():
    # الدخول إلى with يشغّل lifespan فتُنشأ الجداول
    with TestClient(app) as test_client:
        seed()
        yield test_client


@pytest.fixture(scope="session")
def tokens(client):
    result = {}
    for role, email in ACCOUNTS.items():
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        result[role] = response.json()["access_token"]
    return result


@pytest.fixture
def auth(tokens):
    def _headers(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[role]}"}

    return _headers


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def now_utc():
    return datetime.now(timezone.utc)
