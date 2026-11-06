from typing import Any

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator


class VectorType(TypeDecorator):
    """
    نوع متجه يستخدم pgvector على PostgreSQL، ويتراجع إلى JSON على SQLite
    للتجربة المحلية. التخزين على SQLite لا يدعم البحث المتجهي الأصلي،
    لذلك يتم الحساب في طبقة الخدمات (numpy / scikit-learn).
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dimension: int, *args: Any, **kwargs: Any) -> None:
        self.dimension = dimension
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(self.dimension))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]