from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Broadcast, BroadcastChannel, BroadcastScope, User
from app.services.broadcast.hub import list_readers, mark_read, post_broadcast, visible_broadcasts

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])


class BroadcastCreateIn(BaseModel):
    scope: Literal["department", "course"]
    course_id: int | None = None
    title: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=5, max_length=5000)
    is_pinned: bool = False


class BroadcastOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    scope: str
    title: str
    body: str
    is_pinned: bool
    audience_count: int
    seen_count: int
    created_at: datetime


class ReaderOut(BaseModel):
    full_name: str
    read_at: datetime


def _out(b: Broadcast, channel: BroadcastChannel) -> BroadcastOut:
    return BroadcastOut(
        id=b.id,
        channel_id=channel.id,
        channel_name=channel.name,
        scope=channel.scope.value,
        title=b.title,
        body=b.body,
        is_pinned=b.is_pinned,
        audience_count=b.audience_count,
        seen_count=b.seen_count,
        created_at=b.created_at,
    )


@router.post("", response_model=BroadcastOut, status_code=201)
def create_broadcast(
    payload: BroadcastCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BroadcastOut:
    broadcast, channel = post_broadcast(
        db,
        user,
        scope=BroadcastScope(payload.scope),
        course_id=payload.course_id,
        title=payload.title,
        body=payload.body,
        is_pinned=payload.is_pinned,
    )
    return _out(broadcast, channel)


@router.get("", response_model=list[BroadcastOut])
def list_broadcasts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BroadcastOut]:
    return [_out(b, c) for b, c in visible_broadcasts(db, user)]


@router.post("/{broadcast_id}/read", response_model=BroadcastOut)
def read_broadcast(
    broadcast_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BroadcastOut:
    broadcast = mark_read(db, user, broadcast_id)
    channel = db.get(BroadcastChannel, broadcast.channel_id)
    return _out(broadcast, channel)


@router.get("/{broadcast_id}/readers", response_model=list[ReaderOut])
def broadcast_readers(
    broadcast_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReaderOut]:
    return [ReaderOut(full_name=name, read_at=read_at) for name, read_at in list_readers(db, user, broadcast_id)]