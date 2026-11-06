from sqlalchemy import text

from app import models  # noqa: F401  (تسجيل النماذج في Base.metadata)
from app.db.base import Base
from app.db.session import engine


def init() -> None:
    """
    ينشئ امتداد pgvector والجداول. يُشغَّل مرة واحدة قبل تشغيل الخدمات.
    ملاحظة: الجداول تُنشأ بـ create_all حتى تُجمَّد المخططات. بعد ذلك
    أنشئ مراجعة Alembic أولية (alembic revision --autogenerate -m "initial")
    وغيّر أمر خدمة migrate إلى: alembic upgrade head
    """
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    print("Database schema is ready.")


if __name__ == "__main__":
    init()