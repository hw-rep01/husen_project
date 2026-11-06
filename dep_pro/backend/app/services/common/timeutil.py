from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """
    قاعدة التخزين: كل التواريخ في قاعدة البيانات بتوقيت UTC.
    SQLite يعيد قيماً بلا منطقة زمنية، فنفترض أنها UTC.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def local_to_utc(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=local_tz()).astimezone(UTC)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    return local_to_utc(day, time(0)), local_to_utc(day + timedelta(days=1), time(0))


def local_today() -> date:
    return datetime.now(local_tz()).date()