from collections.abc import Iterator
from contextlib import contextmanager

import redis

from app.core.config import get_settings


@contextmanager
def task_lock(name: str, timeout: int) -> Iterator[bool]:
    """
    قفل موزّع عبر Redis يمنع تنفيذ المهمة نفسها في عاملين في وقت واحد.
    لا ينتظر: إذا كان القفل مأخوذاً يُعيد False فيتخطى العامل المهمة.
    مهلة القفل (timeout) تمنع بقاءه معلقاً إذا انهار العامل أثناء التنفيذ.
    """
    client = redis.Redis.from_url(get_settings().redis_url)
    lock = client.lock(f"sdp:lock:{name}", timeout=timeout, blocking=False)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except redis.exceptions.LockError:
                pass  # انتهت المهلة قبل الإفراج، والقفل أُفرج عنه تلقائياً